"""Phase 5. 기업/기술 키워드 언급량 트렌드 — 이동평균 대비 급증 감지."""

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import yaml

from src import issue_tracking

logger = logging.getLogger(__name__)

_ROLLING_WINDOW_DAYS = 7
_SPIKE_RATIO = 2.0
_COLD_START_MIN_COUNT = 3
_HIDDEN_DAYS = 14
_PREVIEW_DAYS = 21


def load_tech_keywords(path) -> list[dict]:
    """config/tech_keywords.yaml을 읽어 기술 키워드 목록을 반환한다.

    Args:
        path: config/tech_keywords.yaml 경로

    Returns:
        [{"canonical": str, "aliases": list[str]}] 리스트
    """
    with Path(path).open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("keywords", [])


def count_company_mentions(articles: list[dict], aliases_config: dict) -> dict[str, int]:
    """기사의 companies 필드(Step 2가 이미 정규화)를 집계해 기업별 언급 건수를 센다.

    Args:
        articles: companies 필드가 포함된 기사 리스트
        aliases_config: config/company_aliases.yaml 로드 결과

    Returns:
        {표기명: 언급 건수} dict
    """
    counts: dict[str, int] = {}
    for article in articles:
        for company_id in article.get("companies") or []:
            name = issue_tracking.entity_display_name(company_id, aliases_config)
            counts[name] = counts.get(name, 0) + 1
    return counts


def match_tech_keywords(text: str, tech_keywords: list[dict]) -> list[str]:
    """텍스트에 언급된 기술 키워드의 canonical 이름 목록을 반환한다.

    Args:
        text: 검색 대상 텍스트
        tech_keywords: load_tech_keywords() 결과

    Returns:
        매칭된 canonical 이름 리스트 (중복 없음, 순서는 tech_keywords 순서)
    """
    matched = []
    for entry in tech_keywords:
        canonical = entry["canonical"]
        terms = [canonical, *entry.get("aliases", [])]
        if any(term in text for term in terms):
            matched.append(canonical)
    return matched


def count_keyword_mentions(articles: list[dict], tech_keywords: list[dict]) -> dict[str, int]:
    """기사 제목+본문에서 매칭되는 기술 키워드별 언급 건수를 센다.

    Args:
        articles: title, raw_text가 포함된 기사 리스트
        tech_keywords: load_tech_keywords() 결과

    Returns:
        {canonical 이름: 언급 건수} dict
    """
    counts: dict[str, int] = {}
    for article in articles:
        text = f"{article.get('title', '')} {article.get('raw_text', '')}"
        for name in match_tech_keywords(text, tech_keywords):
            counts[name] = counts.get(name, 0) + 1
    return counts


def _load_day_counts(trends_dir: Path, day: str, field: str) -> dict[str, int]:
    path = trends_dir / f"{day}.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {item["name"]: item["count"] for item in data.get(field, [])}


def _moving_average(trends_dir: Path, today: str, name: str, field: str) -> float:
    """오늘 이전 _ROLLING_WINDOW_DAYS일의 name 언급 건수 평균(데이터 없는 날은 0)."""
    counts = []
    for days_ago in range(1, _ROLLING_WINDOW_DAYS + 1):
        day = (date.fromisoformat(today) - timedelta(days=days_ago)).isoformat()
        counts.append(_load_day_counts(trends_dir, day, field).get(name, 0))
    return sum(counts) / len(counts) if counts else 0.0


def _build_trend_entries(counts: dict[str, int], trends_dir: Path, today: str, field: str) -> list[dict]:
    entries = []
    for name, count in counts.items():
        avg = _moving_average(trends_dir, today, name, field)
        is_spike = (count / avg >= _SPIKE_RATIO) if avg > 0 else (count >= _COLD_START_MIN_COUNT)
        entries.append({"name": name, "count": count, "is_spike": is_spike})
    return sorted(entries, key=lambda e: e["count"], reverse=True)


def run(
    classified_articles: list[dict],
    aliases_config: dict,
    tech_keywords: list[dict],
    trends_dir: str,
    today: str,
) -> dict:
    """신규 Step. 기업·기술 키워드 언급량을 집계하고 이동평균 대비 급증 여부를 판정한다.

    Args:
        classified_articles: data/classified/YYYY-MM-DD.json 로드 결과 (companies 필드 포함)
        aliases_config: config/company_aliases.yaml 로드 결과
        tech_keywords: load_tech_keywords() 결과
        trends_dir: data/trends 디렉토리 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        {"date","companies": [{"name","count","is_spike"}],"keywords": [...]}
        (trends_dir/{today}.json에도 저장)
    """
    trends_dir = Path(trends_dir)
    company_counts = count_company_mentions(classified_articles, aliases_config)
    keyword_counts = count_keyword_mentions(classified_articles, tech_keywords)

    data = {
        "date": today,
        "companies": _build_trend_entries(company_counts, trends_dir, today, "companies"),
        "keywords": _build_trend_entries(keyword_counts, trends_dir, today, "keywords"),
    }

    trends_dir.mkdir(parents=True, exist_ok=True)
    with (trends_dir / f"{today}.json").open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def count_accumulated_days(trends_dir: str, today: str) -> int:
    """data/trends/*.json 파일 수(오늘 포함) 기준으로 누적 운영 일수를 계산한다.

    Args:
        trends_dir: data/trends 디렉토리 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        누적 운영 일수 (디렉토리가 없으면 1 — 오늘이 첫 실행)
    """
    trends_dir = Path(trends_dir)
    if not trends_dir.exists():
        return 1
    days = {p.stem for p in trends_dir.glob("*.json")}
    days.add(today)
    return len(days)


def cold_start_stage(accumulated_days: int) -> str:
    """콜드 스타트 단계를 판정한다.

    Args:
        accumulated_days: count_accumulated_days() 결과

    Returns:
        "hidden"(14일 미만) | "preview"(14~20일) | "active"(21일 이후)
    """
    if accumulated_days < _HIDDEN_DAYS:
        return "hidden"
    if accumulated_days < _PREVIEW_DAYS:
        return "preview"
    return "active"
