"""Step 2. 중복 제거 — 기업명 정규화 + 결정적(무-LLM) 중복 병합.

과거에는 Gemini로 동일 사건을 클러스터링했으나, 무료 티어 503/429가 잦아 실제로
거의 성공하지 못했다. 그래서 LLM 호출을 완전히 걷어내고 (1) 제목 유사도 그룹핑,
(2) 기업 겹침 + 제목 토큰 유사도 병합의 두 결정적 규칙만으로 중복을 제거한다.
"""

import difflib
import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_TITLE_SIMILARITY_THRESHOLD = 0.9
_TOKEN_JACCARD_THRESHOLD = 0.3
_MIN_TOKEN_LEN = 2
_TOKEN_STRIP_CHARS = ",.\"'…·"


def normalize_company_names(articles: list[dict], aliases_config: dict) -> list[dict]:
    """company_aliases.yaml 매핑을 적용해 기업명을 정규화한다.

    Args:
        articles: Step 1 결과 기사 리스트
        aliases_config: config/company_aliases.yaml 로드 결과

    Returns:
        각 기사에 companies(매칭된 표준 기업 id 리스트) 필드가 추가된 기사 리스트
    """
    for article in articles:
        text = f"{article['title']} {article.get('raw_text', '')}"
        article["companies"] = [
            company_id
            for company_id, info in aliases_config.items()
            if any(alias in text for alias in info.get("aliases", []))
        ]
    return articles


def _normalize_title(title: str) -> str:
    return "".join(title.split())


def group_by_title_similarity(articles: list[dict]) -> list[list[dict]]:
    """제목이 거의 동일한 기사를 사전에 그룹핑한다 (동일 사건의 재배포 기사 등).

    Gemini 클러스터링 호출 전에 적용하는 보조 필터다. 그룹당 대표 1건만 Gemini에 전달해
    호출 기사 수를 줄이고, Gemini 호출이 실패해도 제목이 같은 기사끼리는 폴백에서
    흩어지지 않게 한다.

    Args:
        articles: 기업명 정규화된 기사 리스트

    Returns:
        제목 유사도로 묶인 기사 그룹 리스트 (그룹 내 기사는 이미 같은 사건으로 간주)
    """
    groups: list[list[dict]] = []
    for article in articles:
        normalized = _normalize_title(article["title"])
        for group in groups:
            similarity = difflib.SequenceMatcher(
                None, normalized, _normalize_title(group[0]["title"])
            ).ratio()
            if similarity >= _TITLE_SIMILARITY_THRESHOLD:
                group.append(article)
                break
        else:
            groups.append([article])
    return groups


def assign_title_clusters(articles: list[dict]) -> list[dict]:
    """제목이 거의 동일한 기사끼리 묶어 cluster_id를 부여한다 (LLM 없이 결정적으로 동작).

    표현 차이가 큰 동일 사건은 이 단계 뒤에 merge_near_duplicates()가 기업 겹침 +
    제목 토큰 유사도로 추가 병합한다.

    Args:
        articles: 기업명 정규화된 기사 리스트

    Returns:
        cluster_id가 부여된 기사 리스트
    """
    if not articles:
        return articles

    for group in group_by_title_similarity(articles):
        cluster_id = hashlib.sha1(group[0]["id"].encode("utf-8")).hexdigest()[:12]
        for article in group:
            article["cluster_id"] = cluster_id

    return articles


def _tier_rank(source: str, source_tiers_config: dict) -> int:
    if source in source_tiers_config.get("tier1_원출처", []):
        return 0
    if source in source_tiers_config.get("tier2_전문지", []):
        return 1
    if source in source_tiers_config.get("tier3_재인용", []):
        return 2
    return 3


def pick_representative(cluster_articles: list[dict], source_tiers_config: dict) -> dict:
    """클러스터 내에서 source_tiers.yaml 1차(원출처) 우선으로 대표 기사를 선정한다.

    Args:
        cluster_articles: 동일 cluster_id를 가진 기사 리스트
        source_tiers_config: config/source_tiers.yaml 로드 결과

    Returns:
        대표 기사 dict
    """
    return min(
        cluster_articles,
        key=lambda a: _tier_rank(a["source"], source_tiers_config),
    )


def _title_tokens(title: str) -> set[str]:
    tokens = set()
    for raw in title.split():
        token = raw.strip(_TOKEN_STRIP_CHARS)
        if len(token) >= _MIN_TOKEN_LEN:
            tokens.add(token)
    return tokens


def _token_jaccard(title_a: str, title_b: str) -> float:
    tokens_a, tokens_b = _title_tokens(title_a), _title_tokens(title_b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _is_near_duplicate(article_a: dict, article_b: dict) -> bool:
    """Gemini 클러스터링이 놓친 동일 사건 중복을 잡는 보조 판정.

    기업이 겹치고 제목 토큰 유사도가 임계값 이상이면 동일 사건으로 간주한다. tier가
    다른 경우(원출처 vs 재인용)뿐 아니라, "네이버뉴스 재배포"처럼 서로 다른 원매체의
    기사가 하나의 source 이름으로 뭉뚱그려져 tier가 같아지는 경우도 잡아야 하므로
    tier 일치 여부는 판단에 쓰지 않는다.
    """
    companies_a = set(article_a.get("companies", []))
    companies_b = set(article_b.get("companies", []))
    if not (companies_a & companies_b):
        return False
    return _token_jaccard(article_a["title"], article_b["title"]) >= _TOKEN_JACCARD_THRESHOLD


def merge_near_duplicates(articles: list[dict]) -> list[dict]:
    """assign_title_clusters 결과에 동일 사건 중복 병합을 적용한다.

    제목이 완전히 같지는 않아 제목 그룹핑이 놓친 동일 사건 쌍을, 기업 겹침 + 제목
    토큰 유사도 규칙으로 병합한다.

    Args:
        articles: cluster_id가 부여된 기사 리스트

    Returns:
        병합된 cluster_id가 적용된 기사 리스트
    """
    clusters: dict[str, list[dict]] = {}
    for article in articles:
        clusters.setdefault(article["cluster_id"], []).append(article)

    parent = {cluster_id: cluster_id for cluster_id in clusters}

    def find(cluster_id: str) -> str:
        while parent[cluster_id] != cluster_id:
            cluster_id = parent[cluster_id]
        return cluster_id

    def union(cluster_id_a: str, cluster_id_b: str) -> None:
        root_a, root_b = find(cluster_id_a), find(cluster_id_b)
        if root_a != root_b:
            parent[root_b] = root_a

    cluster_ids = list(clusters.keys())
    for i, cluster_id_a in enumerate(cluster_ids):
        for cluster_id_b in cluster_ids[i + 1 :]:
            if _is_near_duplicate(clusters[cluster_id_a][0], clusters[cluster_id_b][0]):
                union(cluster_id_a, cluster_id_b)

    for article in articles:
        article["cluster_id"] = find(article["cluster_id"])

    return articles


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
    articles = normalize_company_names(raw_articles, aliases_config)
    articles = assign_title_clusters(articles)
    articles = merge_near_duplicates(articles)

    clusters: dict[str, list[dict]] = {}
    for article in articles:
        clusters.setdefault(article["cluster_id"], []).append(article)

    deduped = [pick_representative(members, source_tiers_config) for members in clusters.values()]

    output_path = Path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    return deduped
