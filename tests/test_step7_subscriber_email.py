from pathlib import Path

from src import step5_assemble, step7_subscriber_email as news


def test_build_standalone_html_inlines_css(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-11.html").write_text(
        '<html><head><link rel="stylesheet" href="style.css"></head>'
        "<body>본문</body></html>",
        encoding="utf-8",
    )

    out = news.build_standalone_html(dashboard_dir, "2026-07-11")

    assert '<link rel="stylesheet" href="style.css">' not in out
    assert "<style>" in out
    # 실제 대시보드 CSS의 일부가 인라인됐는지 확인
    assert step5_assemble._DASHBOARD_CSS[:40] in out
    assert "본문" in out


def test_load_subscribers_parses_and_cleans():
    raw = "a@x.com, b@y.com ,a@x.com,  , notanemail , c@z.com"
    assert news.load_subscribers(raw) == ["a@x.com", "b@y.com", "c@z.com"]


def test_load_subscribers_empty_returns_empty_list():
    assert news.load_subscribers("") == []
    assert news.load_subscribers("   ,  ") == []


def test_load_subscribers_reads_env_when_no_arg(monkeypatch):
    monkeypatch.setenv("SUBSCRIBERS", "only@x.com")
    assert news.load_subscribers() == ["only@x.com"]
