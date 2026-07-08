"""Step 2. 중복 제거 — 기업명 정규화 + Gemini 클러스터링."""


def normalize_company_names(articles: list[dict], aliases_config: dict) -> list[dict]:
    """company_aliases.yaml 매핑을 적용해 기업명을 정규화한다.

    Args:
        articles: Step 1 결과 기사 리스트
        aliases_config: config/company_aliases.yaml 로드 결과

    Returns:
        기업명이 정규화된 기사 리스트
    """
    # TODO: alias -> 표준명 매핑 적용
    raise NotImplementedError


def cluster_same_event(articles: list[dict]) -> list[dict]:
    """Gemini API(Flash-Lite)에 제목+본문 앞부분을 배치로 전달해 동일 사건을 클러스터링한다.

    Args:
        articles: 기업명 정규화된 기사 리스트

    Returns:
        cluster_id가 부여된 기사 리스트
    """
    # TODO: gemini_client 호출, "같은 사건 묶기" 프롬프트, JSON 구조화 출력 파싱
    raise NotImplementedError


def pick_representative(cluster_articles: list[dict], source_tiers_config: dict) -> dict:
    """클러스터 내에서 source_tiers.yaml 1차(원출처) 우선으로 대표 기사를 선정한다.

    Args:
        cluster_articles: 동일 cluster_id를 가진 기사 리스트
        source_tiers_config: config/source_tiers.yaml 로드 결과

    Returns:
        대표 기사 dict
    """
    # TODO: tier1 우선, 없으면 tier2, tier3 순
    raise NotImplementedError


def run(
    raw_articles: list[dict],
    aliases_config: dict,
    source_tiers_config: dict,
    output_path: str,
) -> list[dict]:
    """Step 2 진입점.

    Args:
        raw_articles: data/raw/YYYY-MM-DD.json 로드 결과
        aliases_config: config/company_aliases.yaml 로드 결과
        source_tiers_config: config/source_tiers.yaml 로드 결과
        output_path: data/dedup/YYYY-MM-DD.json 저장 경로

    Returns:
        중복 제거된 기사 + cluster_id 리스트
    """
    # TODO: normalize_company_names -> cluster_same_event -> pick_representative -> 저장
    raise NotImplementedError
