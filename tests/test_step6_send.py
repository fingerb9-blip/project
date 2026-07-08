from unittest.mock import patch

from src import step6_send


def test_run_returns_true_when_dashboard_files_exist(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")
    (dashboard_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    assert step6_send.run(str(dashboard_dir), "2026-07-08") is True


@patch("src.step6_send.notify.notify_failure")
def test_run_notifies_and_returns_false_when_daily_html_missing(mock_notify, tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    result = step6_send.run(str(dashboard_dir), "2026-07-08")

    assert result is False
    mock_notify.assert_called_once()
    assert "08:30까지 대시보드 미갱신" in mock_notify.call_args[0][0]


@patch("src.step6_send.notify.notify_failure")
def test_run_notifies_and_returns_false_when_index_missing(mock_notify, tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")

    result = step6_send.run(str(dashboard_dir), "2026-07-08")

    assert result is False
    mock_notify.assert_called_once()
