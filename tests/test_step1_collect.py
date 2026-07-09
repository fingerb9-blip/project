from datetime import datetime, timezone

from src import step1_collect

_RSS_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>테스트 기사</title>
  <link>https://example.com/a</link>
  <pubDate>{pubdate}</pubDate>
  <description>요약</description>
</item>
</channel></rss>
"""


def _rss_with_pubdate(pubdate: str) -> str:
    return _RSS_XML.format(pubdate=pubdate)


def test_fetch_rss_articles_defaults_source_type_to_news():
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    feed = [{"name": "테스트소스", "url": _rss_with_pubdate("Mon, 01 Jan 2024 00:00:00 GMT")}]

    articles = step1_collect.fetch_rss_articles(feed, since)

    assert articles[0]["source_type"] == "언론"


def test_fetch_rss_articles_uses_feed_source_type_override():
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    feed = [
        {
            "name": "IEDM",
            "url": _rss_with_pubdate("Mon, 01 Jan 2024 00:00:00 GMT"),
            "source_type": "학회",
        }
    ]

    articles = step1_collect.fetch_rss_articles(feed, since)

    assert articles[0]["source_type"] == "학회"


def test_fetch_naver_news_tags_source_type_news(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret")

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "items": [
                    {
                        "originallink": "https://example.com/n1",
                        "title": "제목",
                        "description": "설명",
                        "pubDate": "2024-01-01",
                    }
                ]
            }

    monkeypatch.setattr(step1_collect.requests, "get", lambda *a, **k: _Resp())

    articles = step1_collect.fetch_naver_news(["반도체"])

    assert articles[0]["source_type"] == "언론"


def test_fetch_semantic_scholar_papers_tags_source_type_academic(monkeypatch):
    since = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {
                        "title": "HBM paper",
                        "url": "https://example.com/paper1",
                        "abstract": "abstract",
                        "publicationDate": "2024-06-01",
                    }
                ]
            }

    monkeypatch.setattr(step1_collect.requests, "get", lambda *a, **k: _Resp())

    papers = step1_collect.fetch_semantic_scholar_papers(["HBM memory"], since)

    assert papers[0]["source_type"] == "학회"


_KIPRIS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response><body><items>
<item>
  <application_number>1020240012345</application_number>
  <invention_title>고대역폭 메모리 패키징 구조</invention_title>
  <open_date>{open_date}</open_date>
  <abstract_text>초록 내용</abstract_text>
</item>
</items></body></response>
"""


def test_fetch_kipris_patents_returns_empty_without_api_key(monkeypatch):
    monkeypatch.delenv("KIPRIS_API_KEY", raising=False)

    result = step1_collect.fetch_kipris_patents(["HBM"], datetime(2020, 1, 1, tzinfo=timezone.utc))

    assert result == []


def test_fetch_kipris_patents_parses_xml_response(monkeypatch):
    monkeypatch.setenv("KIPRIS_API_KEY", "key")
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)

    class _Resp:
        status_code = 200
        text = _KIPRIS_XML.format(open_date="20240601")

    monkeypatch.setattr(step1_collect.requests, "get", lambda *a, **k: _Resp())

    patents = step1_collect.fetch_kipris_patents(["HBM"], since)

    assert len(patents) == 1
    assert patents[0]["title"] == "고대역폭 메모리 패키징 구조"
    assert patents[0]["source_type"] == "특허"
    assert patents[0]["source"] == "KIPRIS"
    assert "1020240012345" in patents[0]["url"]


def test_fetch_kipris_patents_filters_articles_before_since(monkeypatch):
    monkeypatch.setenv("KIPRIS_API_KEY", "key")
    since = datetime(2024, 6, 2, tzinfo=timezone.utc)

    class _Resp:
        status_code = 200
        text = _KIPRIS_XML.format(open_date="20240601")

    monkeypatch.setattr(step1_collect.requests, "get", lambda *a, **k: _Resp())

    patents = step1_collect.fetch_kipris_patents(["HBM"], since)

    assert patents == []


def test_fetch_kipris_patents_skips_keyword_after_repeated_failure(monkeypatch):
    monkeypatch.setenv("KIPRIS_API_KEY", "key")

    class _Resp:
        status_code = 500
        text = ""

    monkeypatch.setattr(step1_collect.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(step1_collect.time, "sleep", lambda *_: None)

    patents = step1_collect.fetch_kipris_patents(["HBM"], datetime(2020, 1, 1, tzinfo=timezone.utc))

    assert patents == []


def test_fetch_kipris_patents_catches_network_exception_and_skips_keyword(monkeypatch):
    """Verify that network exceptions (timeout, DNS failure, etc.) don't crash the pipeline."""
    import requests
    monkeypatch.setenv("KIPRIS_API_KEY", "key")

    def mock_get_raises(*a, **k):
        raise requests.exceptions.RequestException("Connection failed")

    monkeypatch.setattr(step1_collect.requests, "get", mock_get_raises)
    monkeypatch.setattr(step1_collect.time, "sleep", lambda *_: None)

    # Should return empty list for that keyword instead of raising
    patents = step1_collect.fetch_kipris_patents(["HBM"], datetime(2020, 1, 1, tzinfo=timezone.utc))

    assert patents == []
