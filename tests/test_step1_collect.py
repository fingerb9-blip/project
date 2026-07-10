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


def test_fetch_rss_articles_keeps_entries_despite_encoding_declaration_mismatch():
    """실제 버그 재현: 전자신문/ZDNet Korea는 XML에 us-ascii로 선언돼 있지만 실제로는
    UTF-8이라 feedparser가 bozo=True(CharacterEncodingOverride)를 세운다. entries는
    정상 파싱되므로 접속 실패로 취급해 건너뛰면 안 된다."""
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    xml_with_mismatched_encoding = """<?xml version="1.0" encoding="us-ascii"?>
<rss version="2.0"><channel>
<item>
  <title>테스트 기사</title>
  <link>https://example.com/a</link>
  <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
  <description>요약</description>
</item>
</channel></rss>
"""
    feed = [{"name": "전자신문", "url": xml_with_mismatched_encoding}]

    articles = step1_collect.fetch_rss_articles(feed, since)

    assert len(articles) == 1
    assert articles[0]["title"] == "테스트 기사"


def test_fetch_rss_articles_skips_feed_with_no_entries_after_retries():
    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    empty_feed = '<rss version="2.0"><channel></channel></rss>'
    feed = [{"name": "빈피드", "url": empty_feed}]

    articles = step1_collect.fetch_rss_articles(feed, since)

    assert articles == []


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


def test_fetch_openalex_papers_tags_source_type_academic(monkeypatch):
    since = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "results": [
                    {
                        "title": "HBM paper",
                        "doi": "https://doi.org/10.1000/example",
                        "primary_location": {"landing_page_url": "https://example.com/paper1"},
                        "publication_date": "2024-06-01",
                        "abstract_inverted_index": {"HBM": [0], "abstract": [1]},
                    }
                ]
            }

    monkeypatch.setattr(step1_collect.requests, "get", lambda *a, **k: _Resp())

    papers = step1_collect.fetch_openalex_papers(["HBM memory"], since)

    assert papers[0]["source_type"] == "학회"
    assert papers[0]["source"] == "OpenAlex"
    assert papers[0]["url"] == "https://example.com/paper1"
    assert papers[0]["raw_text"] == "HBM abstract"


def test_fetch_openalex_papers_falls_back_to_doi_when_no_landing_page(monkeypatch):
    since = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "results": [
                    {
                        "title": "HBM paper",
                        "doi": "https://doi.org/10.1000/example",
                        "publication_date": "2024-06-01",
                    }
                ]
            }

    monkeypatch.setattr(step1_collect.requests, "get", lambda *a, **k: _Resp())

    papers = step1_collect.fetch_openalex_papers(["HBM memory"], since)

    assert papers[0]["url"] == "https://doi.org/10.1000/example"
    assert papers[0]["raw_text"] == ""


def test_fetch_openalex_papers_skips_keyword_after_repeated_rate_limit(monkeypatch):
    since = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class _Resp:
        status_code = 429

    monkeypatch.setattr(step1_collect.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(step1_collect.time, "sleep", lambda *_: None)

    papers = step1_collect.fetch_openalex_papers(["HBM memory"], since)

    assert papers == []
