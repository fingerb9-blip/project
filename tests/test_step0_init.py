from src import step0_init


def test_prepare_today_paths_creates_dashboard_dir(tmp_path):
    paths = step0_init.prepare_today_paths(tmp_path, "2026-07-08")

    assert paths["dashboard_dir"] == tmp_path / "data" / "dashboard"
    assert paths["dashboard_dir"].is_dir()
