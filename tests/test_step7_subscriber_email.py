import json
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


def _write_summarized(path, articles):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(articles, ensure_ascii=False), encoding="utf-8")


def test_build_email_body_includes_top_three_and_footer(tmp_path):
    path = tmp_path / "summarized" / "2026-07-11.json"
    arts = [
        {"id": f"a{i}", "title": f"기사{i}", "url": f"https://ex.com/{i}",
         "source": "디일렉", "summary": f"요약{i}", "confirmation_tag": "[확정]",
         "summary_fallback": False, "category": [f"c{i}"], "tier": "핵심"}
        for i in range(5)
    ]
    _write_summarized(path, arts)

    body = news.build_email_body(path, "2026-07-11", "https://site.example/")

    # 상위 3개만 본문에 (select_highlights 기본 규칙상 최대 3개 요청)
    assert body.count('href="https://ex.com/') == 3
    assert "https://site.example/" in body       # 대시보드 링크
    assert "구독" in body and "회신" in body        # 구독취소 안내
    assert "[확정]" in body


def test_build_email_body_handles_no_core(tmp_path):
    path = tmp_path / "summarized" / "2026-07-11.json"
    _write_summarized(path, [])
    body = news.build_email_body(path, "2026-07-11", "https://site.example/")
    assert "핵심 기사가 없습니다" in body
    assert "https://site.example/" in body


def test_build_email_body_missing_file_is_safe(tmp_path):
    path = tmp_path / "summarized" / "2026-07-11.json"  # 존재하지 않음
    body = news.build_email_body(path, "2026-07-11", "https://site.example/")
    assert "핵심 기사가 없습니다" in body
