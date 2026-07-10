"""Step 4. 요약 — Gemini 요약 생성 + 확정/관측 태그."""

import json
import logging
import re
from pathlib import Path

from src import gemini_client, notify

logger = logging.getLogger(__name__)

# 발췌 요약 설정 — Gemini 요약이 없을 때 원문 앞 문장으로 채운다.
_EXTRACT_SENTENCES = 3
_EXTRACT_MAX_CHARS = 300
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _extractive_summary(
    raw_text: str, max_sentences: int = _EXTRACT_SENTENCES, max_chars: int = _EXTRACT_MAX_CHARS
) -> str:
    """Gemini 요약이 없을 때 쓰는 발췌 요약. 원문 앞 문장 몇 개를 잘라 반환한다.

    한국어 뉴스 문장은 대부분 '~다.'로 끝나므로 종결부호(. ! ?) 뒤에서 분리한다.
    문장 구분이 없으면 앞 max_chars만 자른다. raw_text가 비어 있으면 빈 문자열.
    """
    text = (raw_text or "").strip()
    if not text:
        return ""
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    summary = " ".join(sentences[:max_sentences]) if sentences else text
    return summary[:max_chars].rstrip()

_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["id", "summary"],
            },
        }
    },
    "required": ["summaries"],
}

_CONFIRMED_EXPRESSIONS = ["발표했다", "발표"]
_OBSERVED_EXPRESSIONS = ["알려졌다", "알려"]
_RAW_TEXT_LEN = 1500
# 무료 티어 할당량이 넉넉하지 않아 매일 도는 이 호출부터 LITE_MODEL로 전환했다.
# 품질이 부족하면 이 한 줄만 DEFAULT_MODEL로 되돌리면 된다.
_SUMMARY_MODEL = gemini_client.LITE_MODEL


def generate_summaries(articles: list[dict]) -> dict[str, str]:
    """Gemini API(Flash)로 "핵심" 기사 전체를 단일 프롬프트로 배치 요약한다.

    Args:
        articles: "핵심" tier로 분류된 기사 리스트

    Returns:
        {article_id: 3~5문장 요약} dict. 응답에 없는 id는 호출부에서 폴백 처리한다.

    Raises:
        RuntimeError: Gemini 호출 자체가 실패한 경우
    """
    if not articles:
        return {}

    payload = [
        {"id": a["id"], "title": a["title"], "raw_text": a.get("raw_text", "")[:_RAW_TEXT_LEN]}
        for a in articles
    ]
    prompt = (
        "다음은 반도체 업계 뉴스 기사 목록이다. 각 기사를 3~5문장으로 요약하라. "
        "사실관계 위주로 간결하게 작성하고, 근거 없는 추측은 포함하지 않는다. "
        "결과를 summaries 배열로 반환하라.\n\n"
        f"기사 목록: {json.dumps(payload, ensure_ascii=False)}"
    )
    result = gemini_client.call_gemini(prompt, _SUMMARY_SCHEMA, model=_SUMMARY_MODEL)
    return {item["id"]: item["summary"] for item in result.get("summaries", [])}


def tag_confirmation_level(summary: str, source: str, source_tiers_config: dict) -> str:
    """소스 등급 기준으로 [확정]/[관측] 태그를 부여한다.

    1차 원출처는 항상 [확정], 3차 재인용은 항상 [관측]으로 처리한다.
    2차 전문지는 "발표했다" -> 확정, "알려졌다" -> 관측 표현으로 판정하며,
    표현이 모호하면 보수적으로 [관측]을 부여한다.

    Args:
        summary: 생성된 요약 텍스트
        source: 기사 출처
        source_tiers_config: config/source_tiers.yaml 로드 결과

    Returns:
        "[확정]" 또는 "[관측]" 태그 문자열
    """
    if source in source_tiers_config.get("tier1_원출처", []):
        return "[확정]"
    if source in source_tiers_config.get("tier3_재인용", []):
        return "[관측]"

    if any(expr in summary for expr in _CONFIRMED_EXPRESSIONS):
        return "[확정]"
    if any(expr in summary for expr in _OBSERVED_EXPRESSIONS):
        return "[관측]"
    return "[관측]"


def run(
    classified_articles: list[dict],
    source_tiers_config: dict,
    output_path: str,
) -> list[dict]:
    """Step 4 진입점. 요약 실패(API 에러·형식 오류) 시 헤드라인+링크만 폴백 저장한다.

    Args:
        classified_articles: Step 3 결과 기사 리스트 (tier 필드 포함)
        source_tiers_config: config/source_tiers.yaml 로드 결과
        output_path: data/summarized/YYYY-MM-DD.json 저장 경로

    Returns:
        요약 + 확정/관측 태그가 부여된 기사 리스트 ("핵심" tier만)
    """
    core_articles = [a for a in classified_articles if a.get("tier") == "핵심"]

    try:
        summaries = generate_summaries(core_articles)
    except RuntimeError as exc:
        logger.error("배치 요약 실패, 전체 헤드라인+링크로 폴백: %s", exc)
        notify.notify_warning(
            "기사 요약 실패",
            f"Gemini 요약 호출이 실패해 '핵심' 기사 {len(core_articles)}건이 전부 "
            f"헤드라인+링크만 있는 폴백으로 대체됐습니다: {type(exc).__name__}: {exc}",
        )
        summaries = {}

    summarized = []
    for article in core_articles:
        summary = summaries.get(article["id"])
        if summary is None:
            if summaries:
                logger.error("%s 요약 응답 누락, 발췌 요약으로 폴백", article["id"])
            extractive = _extractive_summary(article.get("raw_text", ""))
            if extractive:
                # 원문 앞 문장을 발췌해 채운다. 원문 그대로라 항상 [관측]으로 태깅한다.
                article["summary"] = extractive
                article["confirmation_tag"] = "[관측]"
                article["summary_fallback"] = False
                article["summary_extractive"] = True
            else:
                # 발췌할 원문조차 없을 때만 진짜 폴백(헤드라인+링크).
                article["summary"] = None
                article["confirmation_tag"] = None
                article["summary_fallback"] = True
                article["summary_extractive"] = False
        else:
            article["summary"] = summary
            article["confirmation_tag"] = tag_confirmation_level(summary, article["source"], source_tiers_config)
            article["summary_fallback"] = False
            article["summary_extractive"] = False
        summarized.append(article)

    output_path = Path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summarized, f, ensure_ascii=False, indent=2)

    return summarized
