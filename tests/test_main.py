from pathlib import Path
from unittest.mock import patch

import main


def _paths(tmp_path):
    return {
        "dashboard_dir": tmp_path / "dashboard",
        "summarized": tmp_path / "summarized" / "2026-07-11.json",
        "state": tmp_path / "state" / "run_status.json",
    }


def test_maybe_send_newsletter_calls_step7(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_URL", "https://site.example/")
    with patch("main.step7_subscriber_email.run") as run:
        main._maybe_send_newsletter(tmp_path, _paths(tmp_path), "2026-07-11")
    run.assert_called_once()
    # dashboard_url이 환경변수에서 전달되는지 확인
    assert run.call_args.kwargs.get("dashboard_url") == "https://site.example/" \
        or "https://site.example/" in run.call_args.args


def test_maybe_send_newsletter_swallows_exceptions(tmp_path):
    with patch("main.step7_subscriber_email.run", side_effect=RuntimeError("boom")):
        # 예외가 밖으로 나오면 테스트 실패
        main._maybe_send_newsletter(tmp_path, _paths(tmp_path), "2026-07-11")
