"""Step 1. 수집 — RSS + 네이버 뉴스 검색 API."""

import hashlib
import html
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
# 네이버 뉴스 재배포는 같은 사건을 여러 매체가 반복 보도해 중복·저품질 유입이 많다.
# 키워드당 가져오는 건수(기존 20)를 줄여 재배포 물량 자체를 제한한다.
_NAVER_DISPLAY_PER_KEYWORD = 8


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
        source_type = feed.get("source_type", "언론")

        parsed = None
        for attempt in range(_MAX_RETRIES):
            parsed = feedparser.parse(url)
            if parsed.entries:
                # bozo=True만으로는 접속 실패로 보지 않는다 — 인코딩 선언 불일치 등
                # 경고성 quirk라도 entries가 있으면 정상 수집된 것으로 간주한다.
                break
            logger.warning("%s 접속 재시도 %d/%d: %s", name, attempt + 1, _MAX_RETRIES, url)
            time.sleep(2**attempt)

        if parsed is None or not parsed.entries:
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
                    "source_type": source_type,
                }
            )

    return articles


def _clean_naver_text(text: str) -> str:
    """네이버 검색 API가 반환하는 <b> 하이라이트 태그와 HTML 엔티티를 정리한다."""
    return html.unescape(text.replace("<b>", "").replace("</b>", ""))


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
            params={"query": keyword, "display": _NAVER_DISPLAY_PER_KEYWORD, "sort": "date"},
            timeout=10,
        )
        response.raise_for_status()

        for item in response.json().get("items", []):
            link = item.get("originallink") or item.get("link")
            if not link:
                continue
            articles.append(
                {
                    "id": _make_id(link),
                    "title": _clean_naver_text(item.get("title", "")),
                    "url": link,
                    "source": "네이버뉴스 재배포",
                    "published_at": item.get("pubDate", ""),
                    "raw_text": _clean_naver_text(item.get("description", "")),
                    "source_type": "언론",
                }
            )

    return articles


_PAPER_SOURCE = "OpenAlex"
_OPENALEX_MAX_RETRIES = 3


def _reconstruct_openalex_abstract(inverted_index: dict | None) -> str:
    """OpenAlex의 abstract_inverted_index({단어: [등장 위치, ...]})를 평문으로 복원한다.
    OpenAlex는 저작권 문제로 초록을 위치 인덱스 형태로만 제공한다."""
    if not inverted_index:
        return ""
    max_pos = max(pos for positions in inverted_index.values() for pos in positions)
    words = [""] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words)


def fetch_openalex_papers(keywords: list[str], since: datetime) -> list[dict]:
    """OpenAlex API로 키워드 관련 최신 논문을 보강 수집한다.

    API 키 등록 없이 무료로 호출 가능(공용 요청 풀). title_and_abstract.search 필터로
    제목·초록에 키워드가 실제로 포함된 논문만 매칭해 노이즈를 줄인다. 429/일시 오류는
    재시도 후 그래도 실패하면 해당 키워드만 건너뛴다.

    Args:
        keywords: 검색 키워드 목록 (예: "HBM memory", "EUV lithography")
        since: 수집 기준 시각 (이 시각 이후 발행된 논문만 포함)

    Returns:
        fetch_rss_articles와 동일한 스키마의 기사(논문) dict 리스트
    """
    papers: list[dict] = []

    for keyword in keywords:
        response = None
        for attempt in range(_OPENALEX_MAX_RETRIES):
            response = requests.get(
                "https://api.openalex.org/works",
                params={
                    "filter": f"title_and_abstract.search:{keyword},from_publication_date:{since.date().isoformat()}",
                    "sort": "publication_date:desc",
                    "per-page": 20,
                },
                timeout=10,
            )
            if response.status_code != 429:
                break
            logger.warning(
                "OpenAlex 요청 한도 초과, 재시도 %d/%d: %s",
                attempt + 1,
                _OPENALEX_MAX_RETRIES,
                keyword,
            )
            time.sleep(2**attempt)

        if response is None or response.status_code == 429:
            logger.error("OpenAlex 요청 한도 초과, 키워드 건너뜀: %s", keyword)
            continue
        response.raise_for_status()

        for work in response.json().get("results", []):
            url = (work.get("primary_location") or {}).get("landing_page_url") or work.get("doi")
            if not url:
                continue
            published_at = work.get("publication_date")
            papers.append(
                {
                    "id": _make_id(url),
                    "title": work.get("title") or work.get("display_name") or "",
                    "url": url,
                    "source": _PAPER_SOURCE,
                    "published_at": f"{published_at}T00:00:00+00:00" if published_at else since.isoformat(),
                    "raw_text": _reconstruct_openalex_abstract(work.get("abstract_inverted_index")),
                    "source_type": "학회",
                }
            )

    return papers


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
        feeds_config: sources/feeds.yaml 로드 결과
            ({"feeds": [...], "naver_search_keywords": [...], "paper_search_keywords": [...]})
        output_path: data/raw/YYYY-MM-DD.json 저장 경로

    Returns:
        수집된 기사 배열 (data/raw/YYYY-MM-DD.json에도 저장)
    """
    output_path = Path(output_path)
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    feeds = feeds_config.get("feeds") or []
    keywords = feeds_config.get("naver_search_keywords") or []
    paper_keywords = feeds_config.get("paper_search_keywords") or []

    rss_articles = fetch_rss_articles(feeds, since)
    naver_articles = fetch_naver_news(keywords)
    paper_articles = fetch_openalex_papers(paper_keywords, since)
    articles = rss_articles + naver_articles + paper_articles

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
