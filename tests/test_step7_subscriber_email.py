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


def test_build_email_body_rejects_javascript_url(tmp_path):
    path = tmp_path / "summarized" / "2026-07-11.json"
    arts = [
        {"id": "a0", "title": "위험한 기사", "url": "javascript:alert(1)",
         "source": "디일렉", "summary": "요약", "confirmation_tag": "[확정]",
         "summary_fallback": False, "category": ["c0"], "tier": "핵심"},
    ]
    _write_summarized(path, arts)

    body = news.build_email_body(path, "2026-07-11", "https://site.example/")

    assert 'href="javascript:' not in body
    assert "위험한 기사" in body  # 링크 없이도 제목 텍스트는 노출


def test_build_email_body_escapes_title_html(tmp_path):
    path = tmp_path / "summarized" / "2026-07-11.json"
    arts = [
        {"id": "a0", "title": "<script>alert(1)</script>", "url": "https://ex.com/0",
         "source": "디일렉", "summary": "요약", "confirmation_tag": "[확정]",
         "summary_fallback": False, "category": ["c0"], "tier": "핵심"},
    ]
    _write_summarized(path, arts)

    body = news.build_email_body(path, "2026-07-11", "https://site.example/")

    assert "&lt;script&gt;" in body
    assert "<script>alert(1)</script>" not in body


def _seed(tmp_path):
    dash = tmp_path / "dashboard"; dash.mkdir()
    (dash / "2026-07-11.html").write_text(
        '<html><head><link rel="stylesheet" href="style.css"></head><body>x</body></html>',
        encoding="utf-8")
    summ = tmp_path / "summarized" / "2026-07-11.json"
    summ.parent.mkdir(parents=True, exist_ok=True)
    summ.write_text(json.dumps([{"id": "a1", "title": "T", "url": "https://e.com/1",
        "source": "디일렉", "summary": "s", "confirmation_tag": "[확정]",
        "summary_fallback": False, "category": ["메모리"], "tier": "핵심"}],
        ensure_ascii=False), encoding="utf-8")
    return dash, summ, tmp_path / "state" / "newsletter_state.json"


def test_run_sends_to_each_subscriber_and_records_state(tmp_path):
    dash, summ, state = _seed(tmp_path)
    from unittest.mock import patch
    with patch("src.step7_subscriber_email._send_html_email") as send:
        result = news.run(dash, summ, state, "2026-07-11", "https://site/",
                          subscribers=["a@x.com", "b@y.com"])
    assert send.call_count == 2
    assert result == {"sent": 2, "failed": 0, "skipped": False}
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["last_sent_date"] == "2026-07-11"
    assert saved["sent_count"] == 2


def test_run_skips_when_already_sent_today(tmp_path):
    dash, summ, state = _seed(tmp_path)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"last_sent_date": "2026-07-11", "sent_count": 2}),
                     encoding="utf-8")
    from unittest.mock import patch
    with patch("src.step7_subscriber_email._send_html_email") as send:
        result = news.run(dash, summ, state, "2026-07-11", "https://site/",
                          subscribers=["a@x.com"])
    send.assert_not_called()
    assert result["skipped"] is True


def test_run_force_resend_overrides_guard(tmp_path, monkeypatch):
    dash, summ, state = _seed(tmp_path)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"last_sent_date": "2026-07-11", "sent_count": 1}),
                     encoding="utf-8")
    monkeypatch.setenv("FORCE_RESEND", "true")
    from unittest.mock import patch
    with patch("src.step7_subscriber_email._send_html_email") as send:
        result = news.run(dash, summ, state, "2026-07-11", "https://site/",
                          subscribers=["a@x.com"])
    assert send.call_count == 1
    assert result["skipped"] is False


def test_run_empty_list_sends_nothing(tmp_path):
    dash, summ, state = _seed(tmp_path)
    from unittest.mock import patch
    with patch("src.step7_subscriber_email._send_html_email") as send:
        result = news.run(dash, summ, state, "2026-07-11", "https://site/", subscribers=[])
    send.assert_not_called()
    assert result == {"sent": 0, "failed": 0, "skipped": False}


def test_run_per_recipient_failure_continues_and_counts(tmp_path):
    dash, summ, state = _seed(tmp_path)

    def flaky(to_addr, *a, **k):
        if to_addr == "bad@x.com":
            raise OSError("smtp down")

    from unittest.mock import patch
    with patch("src.step7_subscriber_email._send_html_email", side_effect=flaky):
        result = news.run(dash, summ, state, "2026-07-11", "https://site/",
                          subscribers=["good@x.com", "bad@x.com"])
    assert result == {"sent": 1, "failed": 1, "skipped": False}


def test_run_never_raises_on_unexpected_error(tmp_path):
    # summarized/dashboard가 아예 없어도 예외를 밖으로 던지지 않는다.
    state = tmp_path / "state" / "newsletter_state.json"
    from unittest.mock import patch
    with patch("src.step7_subscriber_email._send_html_email"):
        result = news.run(tmp_path / "nope", tmp_path / "nope.json", state,
                          "2026-07-11", "https://site/", subscribers=["a@x.com"])
    assert "skipped" in result  # 예외 없이 dict 반환


def test_redact_email_masks_local_part_keeps_domain():
    assert news._redact_email("alice@x.com") == "a***@x.com"
    assert news._redact_email("b@y.com") == "b***@y.com"


def test_redact_email_no_at_sign_returns_placeholder():
    assert news._redact_email("notanemail") == "***"


def test_redact_email_empty_returns_placeholder():
    assert news._redact_email("") == "***"


def test_run_per_recipient_failure_log_redacts_email(tmp_path, caplog):
    dash, summ, state = _seed(tmp_path)

    def flaky(to_addr, *a, **k):
        if to_addr == "bad@x.com":
            raise OSError("smtp down")

    from unittest.mock import patch
    with caplog.at_level("ERROR"):
        with patch("src.step7_subscriber_email._send_html_email", side_effect=flaky):
            news.run(dash, summ, state, "2026-07-11", "https://site/",
                      subscribers=["good@x.com", "bad@x.com"])

    assert "bad@x.com" not in caplog.text
    assert "b***@x.com" in caplog.text


def test_build_standalone_html_missing_style_link_returns_unchanged(tmp_path, caplog):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    original = "<html><head></head><body>본문</body></html>"
    (dashboard_dir / "2026-07-11.html").write_text(original, encoding="utf-8")

    with caplog.at_level("WARNING"):
        out = news.build_standalone_html(dashboard_dir, "2026-07-11")

    assert out == original
    assert "style" in caplog.text.lower()


# Tests for fetch_csv_subscribers
from unittest.mock import patch

_CSV = (
    "타임스탬프,이메일 주소,수신 동의\n"
    "2026-07-10 09:00:00,alice@x.com,예\n"
    "2026-07-10 09:01:00,bob@y.com,예\n"
    "2026-07-10 09:02:00,alice@x.com,예\n"      # 중복
    "2026-07-10 09:03:00,notanemail,예\n"        # @ 없음
)


def test_fetch_csv_subscribers_extracts_emails_only(monkeypatch):
    monkeypatch.setattr(news, "_http_get_text", lambda url: _CSV)
    assert news.fetch_csv_subscribers("https://sheet/pub.csv") == ["alice@x.com", "bob@y.com"]


def test_fetch_csv_subscribers_empty_url_returns_empty(monkeypatch):
    called = []
    monkeypatch.setattr(news, "_http_get_text", lambda url: called.append(url) or "")
    assert news.fetch_csv_subscribers("") == []
    assert news.fetch_csv_subscribers("   ") == []
    assert called == []  # 빈 URL이면 HTTP 호출조차 안 함


def test_fetch_csv_subscribers_reads_env_when_no_arg(monkeypatch):
    monkeypatch.setenv("SUBSCRIBERS_CSV_URL", "https://sheet/pub.csv")
    monkeypatch.setattr(news, "_http_get_text", lambda url: "이메일\nc@z.com\n")
    assert news.fetch_csv_subscribers() == ["c@z.com"]


def test_fetch_csv_subscribers_returns_empty_on_fetch_error(monkeypatch):
    def boom(url):
        raise OSError("network down")
    monkeypatch.setattr(news, "_http_get_text", boom)
    assert news.fetch_csv_subscribers("https://sheet/pub.csv") == []


def test_gather_subscribers_merges_env_and_csv(monkeypatch):
    monkeypatch.setattr(news, "load_subscribers", lambda: ["a@x.com", "b@y.com"])
    monkeypatch.setattr(news, "fetch_csv_subscribers", lambda: ["b@y.com", "c@z.com"])
    # env 먼저, CSV의 중복(b@y.com) 제거, 순서 유지
    assert news.gather_subscribers() == ["a@x.com", "b@y.com", "c@z.com"]


def test_run_uses_gather_subscribers_when_no_list(tmp_path, monkeypatch):
    # subscribers=None이면 gather_subscribers 경로를 탄다.
    dash = tmp_path / "dashboard"; dash.mkdir()
    (dash / "2026-07-11.html").write_text(
        '<html><head><link rel="stylesheet" href="style.css"></head><body>x</body></html>',
        encoding="utf-8")
    summ = tmp_path / "summarized" / "2026-07-11.json"
    summ.parent.mkdir(parents=True, exist_ok=True)
    summ.write_text("[]", encoding="utf-8")
    state = tmp_path / "state" / "newsletter_state.json"
    monkeypatch.setattr(news, "gather_subscribers", lambda: ["z@z.com"])
    with patch("src.step7_subscriber_email._send_html_email") as send:
        result = news.run(dash, summ, state, "2026-07-11", "https://site/")
    send.assert_called_once()
    assert send.call_args.args[0] == "z@z.com"
    assert result["sent"] == 1
