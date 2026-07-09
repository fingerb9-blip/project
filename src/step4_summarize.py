"""Step 4. 요약 — Gemini 요약 생성 + 확정/관측 태그."""

import json
import logging
from pathlib import Path

from src import gemini_client

logger = logging.getLogger(__name__)

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
# 실제 응답 품질 비교 전까지는 DEFAULT_MODEL(Flash) 유지. 검증 후 LITE_MODEL로 바꿀 때 이 한 줄만 수정하면 된다.
_SUMMARY_MODEL = gemini_client.DEFAULT_MODEL


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
        summaries = {}

    summarized = []
    for article in core_articles:
        summary = summaries.get(article["id"])
        if summary is None:
            if summaries:
                logger.error("%s 요약 응답 누락, 헤드라인+링크로 폴백", article["id"])
            article["summary"] = None
            article["confirmation_tag"] = None
            article["summary_fallback"] = True
        else:
            article["summary"] = summary
            article["confirmation_tag"] = tag_confirmation_level(summary, article["source"], source_tiers_config)
            article["summary_fallback"] = False
        summarized.append(article)

    output_path = Path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summarized, f, ensure_ascii=False, indent=2)

    return summarized
