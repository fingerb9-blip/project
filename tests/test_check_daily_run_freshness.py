import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_daily_run_freshness  # noqa: E402


@patch("check_daily_run_freshness.notify.notify_failure")
def test_run_returns_true_without_notifying_when_today_succeeded(mock_notify):
    status = {"last_run_date": "2026-07-09", "last_run_status": "success"}

    result = check_daily_run_freshness.run(status, "2026-07-09")

    assert result is True
    mock_notify.assert_not_called()


@patch("check_daily_run_freshness.notify.notify_failure")
def test_run_notifies_when_last_run_date_is_stale(mock_notify):
    """실제 버그 재현: 예약 실행이 러너 배정 실패로 통째로 취소되면 run_status.json이
    전날 날짜로 멈춰 있는데도 워크플로우 내부의 실패 알림 스텝은 실행되지 않는다."""
    status = {"last_run_date": "2026-07-08", "last_run_status": "success"}

    result = check_daily_run_freshness.run(status, "2026-07-09")

    assert result is False
    mock_notify.assert_called_once()
    assert "2026-07-09" in mock_notify.call_args[0][1]
    assert "2026-07-08" in mock_notify.call_args[0][1]


@patch("check_daily_run_freshness.notify.notify_failure")
def test_run_notifies_when_today_ran_but_failed(mock_notify):
    status = {"last_run_date": "2026-07-09", "last_run_status": "failed"}

    result = check_daily_run_freshness.run(status, "2026-07-09")

    assert result is False
    mock_notify.assert_called_once()


@patch("check_daily_run_freshness.notify.notify_failure")
def test_run_notifies_when_status_file_missing(mock_notify):
    result = check_daily_run_freshness.run(None, "2026-07-09")

    assert result is False
    mock_notify.assert_called_once()
