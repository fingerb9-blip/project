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
