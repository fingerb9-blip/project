"""Step 3. 분류 — 키워드 필터링 + Gemini 3단 분류."""


def filter_by_keywords(articles: list[dict], keywords_config: dict) -> list[dict]:
    """keywords.yaml 화이트리스트/블랙리스트로 1차 필터링한다.

    Args:
        articles: Step 2 결과 기사 리스트
        keywords_config: config/keywords.yaml 로드 결과

    Returns:
        블랙리스트 키워드가 제거된 기사 리스트
    """
    # TODO: whitelist/blacklist 매칭
    raise NotImplementedError


def classify_tier_and_category(articles: list[dict], categories_config: dict) -> list[dict]:
    """Gemini API(Flash-Lite)로 핵심/확인 필요/제외 3단 분류 및 카테고리 태깅을 수행한다.

    기업 미특정 + 규제 키워드 매칭 시 "규제·정책"으로 분류한다.

    Args:
        articles: 키워드 필터링된 기사 리스트
        categories_config: config/categories.yaml 로드 결과

    Returns:
        {tier: "핵심"|"확인 필요"|"제외", category: [...]}가 부여된 기사 리스트
    """
    # TODO: gemini_client 호출, 구조화 출력 스키마 지정
    raise NotImplementedError


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
    # TODO: filter_by_keywords -> classify_tier_and_category -> 저장
    raise NotImplementedError
