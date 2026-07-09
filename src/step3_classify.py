"""Step 3. 분류 — 키워드 필터링 + Gemini 3단 분류."""

import json
import logging
from pathlib import Path

from src import gemini_client, notify

logger = logging.getLogger(__name__)

_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "tier": {"type": "string", "enum": ["핵심", "확인 필요", "제외"]},
                    "category": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "tier", "category"],
            },
        }
    },
    "required": ["results"],
}

_REGULATION_CATEGORY = "규제·정책"
_REGULATION_KEYWORD_GROUP = "규제_무역"
_CORE_KEYWORD_GROUP = "반도체_핵심"
# "관세"/"수출통제"는 반도체 무관 기사(자동차 관세, 농산물 수출통제 등)에도 흔히 등장해
# 그 자체로는 반도체 관련성의 증거가 되지 못한다. "반도체법"만 이름 자체로 반도체 특정적이라
# 다른 반도체 신호 없이도 규제·정책 카테고리를 강제할 수 있는 유일한 예외로 둔다.
_UNAMBIGUOUS_REGULATION_TERM = "반도체법"
_SNIPPET_LEN = 300
_TITLE_MATCH_WEIGHT = 3
_BODY_STRONG_WEIGHT = 2
_BODY_WEAK_WEIGHT = 1
_RELEVANCE_EXCLUDE_THRESHOLD = 2


def _matched_keywords(text: str, keyword_group: dict) -> list[str]:
    return [group for group, words in keyword_group.items() if any(w in text for w in words)]


def _find_all_occurrences(text: str, keyword: str) -> list[int]:
    positions = []
    start = 0
    while True:
        idx = text.find(keyword, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def compute_relevance_score(article: dict, core_keywords: list[str]) -> int:
    """제목/본문에서 반도체 핵심 키워드 등장 위치·빈도로 관련도 점수를 매긴다.

    제목에 등장하면 가중치를 높게, 본문 후반부에 1회만 등장하면 낮게 준다.

    Args:
        article: title, raw_text 필드를 포함한 기사 dict
        core_keywords: config/keywords.yaml의 whitelist.반도체_핵심 리스트

    Returns:
        관련도 점수 (높을수록 반도체 관련도가 높음)
    """
    title = article["title"]
    body = article.get("raw_text", "")
    midpoint = len(body) / 2
    score = 0
    for keyword in core_keywords:
        if keyword in title:
            score += _TITLE_MATCH_WEIGHT
            continue
        positions = _find_all_occurrences(body, keyword)
        if not positions:
            continue
        if len(positions) == 1 and positions[0] >= midpoint:
            score += _BODY_WEAK_WEIGHT
        else:
            score += _BODY_STRONG_WEIGHT
    return score


def filter_by_keywords(articles: list[dict], keywords_config: dict) -> list[dict]:
    """keywords.yaml 화이트리스트/블랙리스트로 1차 필터링하고 관련도 점수를 매긴다.

    블랙리스트 키워드가 매칭된 기사는 제외하고, 화이트리스트 매칭 그룹(반도체_핵심 제외)은
    keyword_hints 필드에 남겨 Gemini 분류의 참고 신호로 사용한다. 반도체_핵심 그룹은
    keyword_hints와 별개로 relevance_score 계산에만 사용한다.

    Args:
        articles: Step 2 결과 기사 리스트
        keywords_config: config/keywords.yaml 로드 결과

    Returns:
        블랙리스트 키워드가 제거된 기사 리스트
    """
    whitelist = keywords_config.get("whitelist", {})
    blacklist = keywords_config.get("blacklist", {})
    core_keywords = whitelist.get(_CORE_KEYWORD_GROUP, [])
    hint_whitelist = {k: v for k, v in whitelist.items() if k != _CORE_KEYWORD_GROUP}

    filtered = []
    for article in articles:
        text = f"{article['title']} {article.get('raw_text', '')}"
        if _matched_keywords(text, blacklist):
            continue
        article["keyword_hints"] = _matched_keywords(text, hint_whitelist)
        article["relevance_score"] = compute_relevance_score(article, core_keywords)
        filtered.append(article)

    return filtered


def classify_tier_and_category(articles: list[dict], categories_config: dict) -> list[dict]:
    """Gemini API(Flash-Lite)로 핵심/확인 필요/제외 3단 분류 및 카테고리 태깅을 수행한다.

    기업 미특정 + 규제 키워드 매칭 시 "규제·정책"으로 분류한다.

    Args:
        articles: 키워드 필터링된 기사 리스트
        categories_config: config/categories.yaml 로드 결과

    Returns:
        {tier: "핵심"|"확인 필요"|"제외", category: [...]}가 부여된 기사 리스트
    """
    if not articles:
        return articles

    payload = [
        {
            "id": a["id"],
            "title": a["title"],
            "snippet": a.get("raw_text", "")[:_SNIPPET_LEN],
            "companies": a.get("companies", []),
            "keyword_hints": a.get("keyword_hints", []),
        }
        for a in articles
    ]
    prompt = (
        "다음은 반도체 업계 뉴스 기사 목록이다. 각 기사를 핵심/확인 필요/제외 중 하나로 tier를 매기고, "
        f"카테고리는 다음 중에서 골라라: {list(categories_config.keys())}. "
        "결과를 results 배열로 반환하라.\n\n"
        f"기사 목록: {json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        result = gemini_client.call_gemini(prompt, _CLASSIFY_SCHEMA, model=gemini_client.LITE_MODEL)
        by_id = {r["id"]: r for r in result.get("results", [])}
    except RuntimeError as exc:
        logger.error("분류 실패, 전체 '확인 필요'로 대체: %s", exc)
        notify.notify_warning(
            "기사 분류 실패",
            f"Gemini 분류 호출이 실패해 오늘 기사 {len(articles)}건이 전부 "
            f"'확인 필요'로 대체됐습니다(오늘의 핵심이 비어 보일 수 있음): {type(exc).__name__}: {exc}",
        )
        by_id = {}

    missing_ids = [a["id"] for a in articles if a["id"] not in by_id]
    if by_id and missing_ids:
        notify.notify_warning(
            "기사 분류 일부 실패",
            f"Gemini 응답에 {len(missing_ids)}/{len(articles)}건의 분류 결과가 빠져 "
            "해당 기사는 '확인 필요'로 대체됐습니다.",
        )

    for article in articles:
        result = by_id.get(article["id"], {"tier": "확인 필요", "category": []})
        article["tier"] = result["tier"]
        article["category"] = list(result["category"])
        no_company = not article.get("companies")
        has_regulation_hint = _REGULATION_KEYWORD_GROUP in article.get("keyword_hints", [])
        text = f"{article.get('title', '')} {article.get('raw_text', '')}"
        has_semiconductor_signal = (
            article.get("relevance_score", 0) > 0 or _UNAMBIGUOUS_REGULATION_TERM in text
        )
        if (
            no_company
            and has_regulation_hint
            and has_semiconductor_signal
            and _REGULATION_CATEGORY not in article["category"]
        ):
            article["category"].append(_REGULATION_CATEGORY)

        low_relevance = article.get("relevance_score", 0) <= _RELEVANCE_EXCLUDE_THRESHOLD
        if low_relevance and not article.get("keyword_hints") and not article.get("companies"):
            article["tier"] = "제외"

    return articles


def run(
    dedup_articles: list[dict],
    categories_config: dict,
    keywords_config: dict,
    output_path: str,
) -> list[dict]:
    """Step 3 진입점.

    Args:
        dedup_articles: data/dedup/YYYY-MM-DD.json 로드 결과
        categories_config: config/categories.yaml 로드 결과
        keywords_config: config/keywords.yaml 로드 결과
        output_path: data/classified/YYYY-MM-DD.json 저장 경로

    Returns:
        tier/category가 부여된 기사 리스트
    """
    articles = filter_by_keywords(dedup_articles, keywords_config)
    articles = classify_tier_and_category(articles, categories_config)

    output_path = Path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    return articles
