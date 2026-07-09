from src import radar_weekly


def test_load_tracked_companies_reads_yaml(tmp_path):
    path = tmp_path / "radar_companies.yaml"
    path.write_text("companies:\n  - samsung_electronics\n  - tsmc\n", encoding="utf-8")

    result = radar_weekly.load_tracked_companies(path)

    assert result == ["samsung_electronics", "tsmc"]


def test_week_label_formats_iso_week():
    assert radar_weekly.week_label("2026-07-09") == "2026-W28"


def test_week_label_pads_single_digit_week():
    assert radar_weekly.week_label("2026-01-01") == "2026-W01"
