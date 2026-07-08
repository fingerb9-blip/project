"""Step 1. 수집 — RSS + 네이버 뉴스 검색 API."""

import hashlib
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

from src import notify

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_CONSECUTIVE_ZERO_DAYS = 3


def _make_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _parse_published(entry) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        value = getattr(entry, key, None)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc).isoformat()
    return None


def fetch_rss_articles(feed_urls: list[dict], since: datetime) -> list[dict]:
    """feedparser로 각 RSS 소스를 순회해 최근 24시간 내 기사만 필터링한다.

    접속 실패 소스는 3회 재시도(exponential backoff), 최종 실패 시 로그만 남기고 계속 진행한다.

    Args:
        feed_urls: sources/feeds.yaml의 feeds 목록 ({"name", "url"} dict 리스트)
        since: 수집 기준 시각 (현재 - 24h)

    Returns:
        {title, url, source, published_at, raw_text} 형태의 기사 dict 리스트
    """
    articles: list[dict] = []

    for feed in feed_urls:
        name = feed["name"]
        url = feed["url"]

        parsed = None
        for attempt in range(_MAX_RETRIES):
            parsed = feedparser.parse(url)
            if not parsed.bozo:
                break
            logger.warning("%s 접속 재시도 %d/%d: %s", name, attempt + 1, _MAX_RETRIES, url)
            time.sleep(2**attempt)

        if parsed is None or parsed.bozo:
            logger.error("%s 소스 %d회 연속 접속 실패, 건너뜀: %s", name, _MAX_RETRIES, url)
            continue

        for entry in parsed.entries:
            published_at = _parse_published(entry)
            if published_at and datetime.fromisoformat(published_at) < since:
                continue
            link = entry.get("link", "")
            if not link:
                continue
            articles.append(
                {
                    "id": _make_id(link),
                    "title": entry.get("title", ""),
                    "url": link,
                    "source": name,
                    "published_at": published_at or since.isoformat(),
                    "raw_text": entry.get("summary", ""),
                }
            )

    return articles


def fetch_naver_news(keywords: list[str]) -> list[dict]:
    """네이버 뉴스 검색 API로 국내 키워드 기사를 보강 수집한다.

    Args:
        keywords: 검색 키워드 목록

    Returns:
        fetch_rss_articles와 동일한 스키마의 기사 dict 리스트
    """
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        logger.warning("NAVER_CLIENT_ID/SECRET 미설정, 네이버 뉴스 보강 수집을 건너뜁니다")
        return []

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    articles: list[dict] = []

    for keyword in keywords:
        response = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers=headers,
            params={"query": keyword, "display": 20, "sort": "date"},
            timeout=10,
        )
        response.raise_for_status()

        for item in response.json().get("items", []):
            link = item.get("originallink") or item.get("link")
            if not link:
                continue
            title = item["title"].replace("<b>", "").replace("</b>", "")
            articles.append(
                {
                    "id": _make_id(link),
                    "title": title,
                    "url": link,
                    "source": "네이버뉴스 재배포",
                    "published_at": item.get("pubDate", ""),
                    "raw_text": item.get("description", ""),
                }
            )

    return articles


def _check_consecutive_zero(raw_dir: Path, source: str, today_count: int) -> bool:
    """오늘 포함 최근 N일간 해당 source가 연속 0건인지 확인한다 ("조용한 품질 열화" 감지)."""
    if today_count > 0:
        return False

    for days_ago in range(1, _CONSECUTIVE_ZERO_DAYS):
        day = (date.today() - timedelta(days=days_ago)).isoformat()
        raw_path = raw_dir / f"{day}.json"
        if not raw_path.exists():
            return False
        with raw_path.open(encoding="utf-8") as f:
            prev_articles = json.load(f)
        if any(a.get("source") == source for a in prev_articles):
            return False

    return True


def run(feeds_config: dict, output_path: str) -> list[dict]:
    """Step 1 진입점. 특정 소스 3회 연속 0건이면 경고 알림을 발송한다.

    Args:
        feeds_config: sources/feeds.yaml 로드 결과 ({"feeds": [...], "naver_search_keywords": [...]})
        output_path: data/raw/YYYY-MM-DD.json 저장 경로

    Returns:
        수집된 기사 배열 (data/raw/YYYY-MM-DD.json에도 저장)
    """
    output_path = Path(output_path)
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    feeds = feeds_config.get("feeds") or []
    keywords = feeds_config.get("naver_search_keywords") or []

    rss_articles = fetch_rss_articles(feeds, since)
    naver_articles = fetch_naver_news(keywords)
    articles = rss_articles + naver_articles

    for feed in feeds:
        name = feed["name"]
        today_count = sum(1 for a in rss_articles if a["source"] == name)
        if _check_consecutive_zero(output_path.parent, name, today_count):
            notify.notify_warning(
                "소스 품질 열화",
                f"{name} 소스가 최근 {_CONSECUTIVE_ZERO_DAYS}일 연속 0건입니다.",
            )

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    return articles
