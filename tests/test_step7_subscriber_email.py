from src import step7_subscriber_email as news


def test_load_subscribers_parses_and_cleans():
    raw = "a@x.com, b@y.com ,a@x.com,  , notanemail , c@z.com"
    assert news.load_subscribers(raw) == ["a@x.com", "b@y.com", "c@z.com"]


def test_load_subscribers_empty_returns_empty_list():
    assert news.load_subscribers("") == []
    assert news.load_subscribers("   ,  ") == []


def test_load_subscribers_reads_env_when_no_arg(monkeypatch):
    monkeypatch.setenv("SUBSCRIBERS", "only@x.com")
    assert news.load_subscribers() == ["only@x.com"]
