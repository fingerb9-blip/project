"""Phase 4. 경쟁 구도 레이더 — 주간 기업별 언급량·톤·핵심 이슈 집계."""

import json
from datetime import date, timedelta
from pathlib import Path

import yaml


def load_tracked_companies(radar_companies_path) -> list[str]:
    """config/radar_companies.yaml을 읽어 집계 대상 기업 id 목록을 반환한다.

    Args:
        radar_companies_path: config/radar_companies.yaml 경로

    Returns:
        기업 id 목록 (config/company_aliases.yaml의 키와 일치)
    """
    with Path(radar_companies_path).open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("companies", [])


def week_label(today: str) -> str:
    """YYYY-MM-DD 날짜를 ISO 주차 표기(YYYY-Www)로 변환한다.

    Args:
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        "YYYY-Www" 형식 문자열 (예: "2026-W28")
    """
    iso_year, iso_week, _ = date.fromisoformat(today).isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


_WINDOW_DAYS = 7


def load_week_dedup_articles(dedup_dir, today: str, days: int = _WINDOW_DAYS) -> list[dict]:
    """최근 days일치 data/dedup/YYYY-MM-DD.json을 모두 읽어 합친다.

    Args:
        dedup_dir: data/dedup 디렉토리 경로
        today: YYYY-MM-DD 형식 날짜 문자열 (집계 기준일, 포함)
        days: 집계 기간(일)

    Returns:
        기간 내 존재하는 파일들의 기사 리스트를 합친 결과 (파일 없는 날은 건너뜀)
    """
    dedup_dir = Path(dedup_dir)
    articles: list[dict] = []
    for days_ago in range(days):
        day = (date.fromisoformat(today) - timedelta(days=days_ago)).isoformat()
        path = dedup_dir / f"{day}.json"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            articles.extend(json.load(f))
    return articles


def aggregate_mentions(articles: list[dict], tracked_companies: list[str]) -> dict[str, int]:
    """기업별 이번 주 언급 기사 수를 집계한다.

    Args:
        articles: load_week_dedup_articles 결과 (companies 필드 포함)
        tracked_companies: 집계 대상 기업 id 목록

    Returns:
        {회사id: 언급 기사 수} (모든 tracked_companies 키 포함, 언급 없으면 0)
    """
    counts = {company: 0 for company in tracked_companies}
    for article in articles:
        for company in article.get("companies") or []:
            if company in counts:
                counts[company] += 1
    return counts


def group_articles_by_company(articles: list[dict], tracked_companies: list[str]) -> dict[str, list[dict]]:
    """기업별로 해당 기업이 언급된 기사 리스트를 묶는다 (톤 판정 입력용).

    Args:
        articles: load_week_dedup_articles 결과
        tracked_companies: 집계 대상 기업 id 목록

    Returns:
        {회사id: 기사 리스트} (모든 tracked_companies 키 포함, 언급 없으면 빈 리스트)
    """
    grouped: dict[str, list[dict]] = {company: [] for company in tracked_companies}
    for article in articles:
        for company in article.get("companies") or []:
            if company in grouped:
                grouped[company].append(article)
    return grouped
