"""Phase 4. 경쟁 구도 레이더 — 주간 기업별 언급량·톤·핵심 이슈 집계."""

from datetime import date
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
