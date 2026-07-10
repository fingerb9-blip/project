from src import step0_init


def test_prepare_today_paths_creates_dashboard_dir(tmp_path):
    paths = step0_init.prepare_today_paths(tmp_path, "2026-07-08")

    assert paths["dashboard_dir"] == tmp_path / "data" / "dashboard"
    assert paths["dashboard_dir"].is_dir()


def test_prepare_today_paths_includes_phase3_state_paths(tmp_path):
    paths = step0_init.prepare_today_paths(tmp_path, "2026-07-08")

    assert paths["issues"] == tmp_path / "data" / "state" / "issues.json"
    assert paths["frequency_baseline"] == tmp_path / "data" / "state" / "frequency_baseline.json"
    assert paths["issues"].parent.is_dir()


def test_prepare_today_paths_includes_stock_prices_path(tmp_path):
    paths = step0_init.prepare_today_paths(tmp_path, "2026-07-08")

    assert paths["stock_prices"] == tmp_path / "data" / "state" / "stock_prices.json"
