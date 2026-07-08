"""Step 4. 요약 — Gemini 요약 생성 + 확정/관측 태그."""


def summarize_article(article: dict) -> str:
    """Gemini API(Flash)로 기사당 3~5문장 요약을 생성한다.

    Args:
        article: "핵심" tier로 분류된 기사 dict

    Returns:
        3~5문장 요약 텍스트
    """
    # TODO: gemini_client 호출
    raise NotImplementedError


def tag_confirmation_level(summary: str, source: str, source_tiers_config: dict) -> str:
    """소스 등급 기준으로 [확정]/[관측] 태그를 부여한다.

    2차 소스는 "발표했다" -> 확정, "알려졌다" -> 관측으로 판정한다.

    Args:
        summary: 생성된 요약 텍스트
        source: 기사 출처
        source_tiers_config: config/source_tiers.yaml 로드 결과

    Returns:
        "[확정]" 또는 "[관측]" 태그 문자열
    """
    # TODO: 표현 패턴 매칭
    raise NotImplementedError


def run(
    classified_articles: list[dict],
    source_tiers_config: dict,
    output_path: str,
) -> list[dict]:
    """Step 4 진입점. 요약 실패(API 에러·형식 오류) 시 헤드라인+링크만 폴백 저장한다.

    Args:
        classified_articles: "핵심" tier로 필터링된 기사 리스트
        source_tiers_config: config/source_tiers.yaml 로드 결과
        output_path: data/summarized/YYYY-MM-DD.json 저장 경로

    Returns:
        요약 + 확정/관측 태그가 부여된 기사 리스트
    """
    # TODO: summarize_article -> tag_confirmation_level, 실패 시 폴백
    raise NotImplementedError
