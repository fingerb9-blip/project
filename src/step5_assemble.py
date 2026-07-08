"""Step 5. 조립 — 브리핑 마크다운/HTML 문서 생성."""


def build_briefing(summarized_articles: list[dict], collection_stats: dict) -> str:
    """오늘의 핵심 -> 카테고리별 -> 확인 필요 목록 -> 수집 상태 순으로 브리핑 문서를 조립한다.

    Args:
        summarized_articles: Step 4 결과 기사 리스트
        collection_stats: 소스별 오늘 건수 vs 최근 7일 평균 통계

    Returns:
        마크다운 형식의 브리핑 문서 문자열
    """
    # TODO: 섹션별 조립, 템플릿 적용
    raise NotImplementedError


def run(summarized_articles: list[dict], collection_stats: dict, output_path: str) -> str:
    """Step 5 진입점.

    Args:
        summarized_articles: data/summarized/YYYY-MM-DD.json 로드 결과
        collection_stats: 소스별 수집 통계
        output_path: data/archive/YYYY-MM-DD.md 저장 경로

    Returns:
        생성된 브리핑 문서 문자열 (output_path에도 저장)
    """
    # TODO: build_briefing -> 파일 저장
    raise NotImplementedError
