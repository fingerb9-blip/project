"""Step 4. 요약 — Gemini 요약 생성 + 확정/관측 태그."""

import json
import logging
from pathlib import Path

from src import gemini_client

logger = logging.getLogger(__name__)

_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}

_CONFIRMED_EXPRESSIONS = ["발표했다", "발표"]
_OBSERVED_EXPRESSIONS = ["알려졌다", "알려"]


def summarize_article(article: dict) -> str:
    """Gemini API(Flash)로 기사당 3~5문장 요약을 생성한다.

    Args:
        article: "핵심" tier로 분류된 기사 dict

    Returns:
        3~5문장 요약 텍스트
    """
    prompt = (
        "다음 반도체 업계 뉴스 기사를 3~5문장으로 요약하라. "
        "사실관계 위주로 간결하게 작성하고, 근거 없는 추측은 포함하지 않는다.\n\n"
        f"제목: {article['title']}\n"
        f"본문: {article.get('raw_text', '')}"
    )
    result = gemini_client.call_gemini(prompt, _SUMMARY_SCHEMA, model=gemini_client.DEFAULT_MODEL)
    return result["summary"]


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
    summarized = []

    for article in core_articles:
        try:
            summary = summarize_article(article)
            tag = tag_confirmation_level(summary, article["source"], source_tiers_config)
            article["summary"] = summary
            article["confirmation_tag"] = tag
            article["summary_fallback"] = False
        except RuntimeError as exc:
            logger.error("%s 요약 실패, 헤드라인+링크로 폴백: %s", article["id"], exc)
            article["summary"] = None
            article["confirmation_tag"] = None
            article["summary_fallback"] = True
        summarized.append(article)

    output_path = Path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summarized, f, ensure_ascii=False, indent=2)

    return summarized
