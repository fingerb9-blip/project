"""Step 2. 중복 제거 — 기업명 정규화 + Gemini 클러스터링."""

import difflib
import hashlib
import json
import logging
from pathlib import Path

from src import gemini_client

logger = logging.getLogger(__name__)

_CLUSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
    },
    "required": ["clusters"],
}

_SNIPPET_LEN = 300
_TITLE_SIMILARITY_THRESHOLD = 0.9


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


def cluster_same_event(articles: list[dict], source_tiers_config: dict) -> list[dict]:
    """제목 유사도로 사전 그룹핑한 뒤, 그룹 대표만 Gemini API(Flash-Lite)에 배치로 전달해
    동일 사건을 클러스터링한다.

    Args:
        articles: 기업명 정규화된 기사 리스트
        source_tiers_config: config/source_tiers.yaml 로드 결과 (프롬프트 힌트에 사용)

    Returns:
        cluster_id가 부여된 기사 리스트
    """
    if not articles:
        return articles

    groups = group_by_title_similarity(articles)
    representatives = [group[0] for group in groups]

    payload = [
        {
            "id": a["id"],
            "title": a["title"],
            "snippet": a.get("raw_text", "")[:_SNIPPET_LEN],
            "companies": a.get("companies", []),
            "source_tier": _tier_label(a["source"], source_tiers_config),
        }
        for a in representatives
    ]
    prompt = (
        "다음은 오늘 수집된 반도체 업계 뉴스 기사 목록이다. "
        "같은 사건(동일 발표·계약·인사 등)을 다루는 기사끼리 id를 묶어 clusters 배열로 반환하라. "
        "companies가 겹치고 source_tier가 다른 두 기사(예: 원출처의 공식 발표와 "
        "전문지·재인용 매체의 후속 보도)는 표현이 달라도 같은 사건이면 반드시 같은 클러스터로 묶어라. "
        "서로 다른 사건이면 별도 클러스터로 둔다.\n\n"
        f"기사 목록: {json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        result = gemini_client.call_gemini(prompt, _CLUSTER_SCHEMA, model=gemini_client.LITE_MODEL)
        clusters = result.get("clusters", [])
    except RuntimeError as exc:
        logger.error("클러스터링 실패, 제목 유사도 그룹 단위로 대체: %s", exc)
        clusters = []

    rep_id_to_cluster: dict[str, str] = {}
    for member_ids in clusters:
        if not member_ids:
            continue
        cluster_id = hashlib.sha1("|".join(sorted(member_ids)).encode("utf-8")).hexdigest()[:12]
        for member_id in member_ids:
            rep_id_to_cluster[member_id] = cluster_id

    for group in groups:
        rep_id = group[0]["id"]
        if rep_id not in rep_id_to_cluster:
            rep_id_to_cluster[rep_id] = hashlib.sha1(rep_id.encode("utf-8")).hexdigest()[:12]
        cluster_id = rep_id_to_cluster[rep_id]
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


def _tier_label(source: str, source_tiers_config: dict) -> str:
    labels = {0: "원출처", 1: "전문지", 2: "재인용", 3: "미분류"}
    return labels[_tier_rank(source, source_tiers_config)]


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
    articles = cluster_same_event(articles, source_tiers_config)

    clusters: dict[str, list[dict]] = {}
    for article in articles:
        clusters.setdefault(article["cluster_id"], []).append(article)

    deduped = [pick_representative(members, source_tiers_config) for members in clusters.values()]

    output_path = Path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    return deduped
