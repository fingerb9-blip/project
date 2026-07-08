"""Step 1. 수집 — RSS + 네이버 뉴스 검색 API."""

from datetime import datetime


def fetch_rss_articles(feed_urls: list[str], since: datetime) -> list[dict]:
    """feedparser로 각 RSS 소스를 순회해 최근 24시간 내 기사만 필터링한다.

    접속 실패 소스는 3회 재시도(exponential backoff), 최종 실패 시 로그만 남기고 계속 진행한다.

    Args:
        feed_urls: sources/feeds.yaml에서 로드한 URL 목록
        since: 수집 기준 시각 (현재 - 24h)

    Returns:
        {title, url, source, published_at, raw_text} 형태의 기사 dict 리스트
    """
    # TODO: feedparser 순회, 3회 재시도 backoff, 정규화
    raise NotImplementedError


def fetch_naver_news(keywords: list[str]) -> list[dict]:
    """네이버 뉴스 검색 API로 국내 키워드 기사를 보강 수집한다.

    Args:
        keywords: 검색 키워드 목록

    Returns:
        fetch_rss_articles와 동일한 스키마의 기사 dict 리스트
    """
    # TODO: 네이버 뉴스 검색 API 호출
    raise NotImplementedError


def run(feeds_config: dict, output_path: str) -> list[dict]:
    """Step 1 진입점. 특정 소스 3회 연속 0건이면 소스 상태 경고 로그를 남긴다.

    Args:
        feeds_config: sources/feeds.yaml 로드 결과
        output_path: data/raw/YYYY-MM-DD.json 저장 경로

    Returns:
        수집된 기사 배열 (data/raw/YYYY-MM-DD.json에도 저장)
    """
    # TODO: fetch_rss_articles + fetch_naver_news 병합, id=sha1(url) 부여, 저장
    raise NotImplementedError
