"""통계 대시보드 데이터 생성 — 일별 통계 집계 + 전체 병합 캐시.

data/dashboard/stats/YYYY-MM-DD.json(일별)과 stats_all.json(전체 병합, 매 실행마다
전체 재계산)을 만든다. dashboard.html은 이 정적 JSON만 fetch해서 그리므로, 여기서는
집계·저장만 하고 렌더링은 하지 않는다.
"""

import json
from pathlib import Path

from src import step5_assemble

_TOP_KEYWORDS_LIMIT = 10
_EXCLUDED_TIER = "제외"


def compute_daily_stats(
    classified_articles: list[dict], summarized_articles: list[dict], date: str
) -> dict:
    """하루치 기사로 통계 dict를 만든다.

    total_articles/by_category/by_source는 tier="제외"를 뺀 그날의 모든 분류 기사를
    대상으로 한다. by_confidence는 확정/관측/요약없음 개념이 있는 "핵심" tier(요약
    완료) 기사만 대상으로 한다 — "확인 필요" 기사는 아직 신뢰도 태그가 없다.
    top_keywords는 기존 실시간 트렌드 섹션과 동일한 회사/기술명 사전 매칭
    (step5_assemble._compute_keyword_trends)을 재사용한다.

    Args:
        classified_articles: Step 3 결과 (모든 tier)
        summarized_articles: Step 4 결과 ("핵심" tier, 요약/신뢰도 태그 포함)
        date: YYYY-MM-DD

    Returns:
        stats/YYYY-MM-DD.json 스키마 dict. noise_reported는 항상 0이다 — "노이즈로
        표시"가 브라우저 localStorage에만 남는 로컬 숨김 방식이라 서버는 실제 신고
        건수를 알 수 없다.
    """
    covered = [a for a in classified_articles if a.get("tier") != _EXCLUDED_TIER]

    by_category: dict[str, int] = {}
    for article in covered:
        for category in step5_assemble._split_categories(article.get("category") or []):
            by_category[category] = by_category.get(category, 0) + 1

    by_source: dict[str, int] = {}
    for article in covered:
        source = article.get("source", "")
        by_source[source] = by_source.get(source, 0) + 1

    by_confidence = {"확정": 0, "관측": 0, "요약없음": 0}
    for article in summarized_articles:
        if article.get("summary_fallback"):
            by_confidence["요약없음"] += 1
            continue
        tag = article.get("confirmation_tag") or ""
        if "확정" in tag:
            by_confidence["확정"] += 1
        elif "관측" in tag:
            by_confidence["관측"] += 1

    trend_input = [{"title": a.get("title", ""), "summary": a.get("raw_text", "")} for a in covered]
    trends = step5_assemble._compute_keyword_trends(trend_input, top_n=_TOP_KEYWORDS_LIMIT)
    top_keywords = [{"keyword": t["keyword"], "count": t["count"]} for t in trends if t["keyword"] != "기타"]

    return {
        "date": date,
        "total_articles": len(covered),
        "by_category": by_category,
        "by_source": by_source,
        "by_confidence": by_confidence,
        "top_keywords": top_keywords,
        "noise_reported": 0,
    }


def save_daily_stats(stats_dir: Path, stats: dict) -> Path:
    """일별 통계를 stats/YYYY-MM-DD.json으로 저장한다.

    Args:
        stats_dir: data/dashboard/stats 디렉토리 경로
        stats: compute_daily_stats() 결과

    Returns:
        저장된 파일 경로
    """
    stats_dir = Path(stats_dir)
    stats_dir.mkdir(parents=True, exist_ok=True)
    path = stats_dir / f"{stats['date']}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    return path


def build_stats_all(stats_dir: Path) -> list[dict]:
    """stats_dir의 모든 일별 통계 파일을 훑어 날짜 오름차순으로 합친다.

    누적 append가 아니라 매번 전체를 다시 스캔해 재계산한다 — 과거 일별 파일의
    집계 로직이 수정돼도 stats_all.json만 다시 만들면 반영된다.

    Args:
        stats_dir: data/dashboard/stats 디렉토리 경로

    Returns:
        날짜 오름차순으로 정렬된 통계 dict 리스트 (stats_all.json에도 저장)
    """
    stats_dir = Path(stats_dir)
    stats_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for path in sorted(stats_dir.glob("*.json")):
        if path.stem == "stats_all":
            continue
        with path.open(encoding="utf-8") as f:
            entries.append(json.load(f))
    entries.sort(key=lambda e: e["date"])

    with (stats_dir / "stats_all.json").open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    return entries


def run(
    classified_articles: list[dict], summarized_articles: list[dict], date: str, stats_dir: str
) -> list[dict]:
    """Step 진입점. 오늘 통계를 저장하고 전체 병합본을 다시 만든다.

    Args:
        classified_articles: Step 3 결과 (모든 tier)
        summarized_articles: Step 4 결과 ("핵심" tier)
        date: YYYY-MM-DD
        stats_dir: data/dashboard/stats 디렉토리 경로

    Returns:
        build_stats_all() 결과 (날짜 오름차순 통계 리스트)
    """
    stats_dir = Path(stats_dir)
    stats = compute_daily_stats(classified_articles, summarized_articles, date)
    save_daily_stats(stats_dir, stats)
    return build_stats_all(stats_dir)
