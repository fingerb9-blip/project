import json
from unittest.mock import patch

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


def test_load_week_dedup_articles_reads_available_days(tmp_path):
    dedup_dir = tmp_path / "dedup"
    dedup_dir.mkdir()
    (dedup_dir / "2026-07-09.json").write_text(
        json.dumps([{"id": "a1", "title": "t1", "companies": ["samsung_electronics"]}]),
        encoding="utf-8",
    )
    (dedup_dir / "2026-07-08.json").write_text(
        json.dumps([{"id": "a2", "title": "t2", "companies": ["sk_hynix"]}]),
        encoding="utf-8",
    )

    articles = radar_weekly.load_week_dedup_articles(dedup_dir, "2026-07-09", days=7)

    assert {a["id"] for a in articles} == {"a1", "a2"}


def test_load_week_dedup_articles_skips_missing_days(tmp_path):
    dedup_dir = tmp_path / "dedup"
    dedup_dir.mkdir()
    (dedup_dir / "2026-07-09.json").write_text(
        json.dumps([{"id": "a1", "title": "t1", "companies": []}]), encoding="utf-8"
    )

    articles = radar_weekly.load_week_dedup_articles(dedup_dir, "2026-07-09", days=7)

    assert len(articles) == 1


def test_aggregate_mentions_counts_per_company():
    articles = [
        {"companies": ["samsung_electronics", "tsmc"]},
        {"companies": ["samsung_electronics"]},
        {"companies": ["sk_hynix"]},
    ]
    counts = radar_weekly.aggregate_mentions(
        articles, ["samsung_electronics", "sk_hynix", "tsmc", "intel"]
    )
    assert counts == {"samsung_electronics": 2, "sk_hynix": 1, "tsmc": 1, "intel": 0}


def test_aggregate_mentions_ignores_untracked_companies():
    articles = [{"companies": ["some_other_company"]}]
    counts = radar_weekly.aggregate_mentions(articles, ["samsung_electronics"])
    assert counts == {"samsung_electronics": 0}


def test_group_articles_by_company_buckets_articles():
    articles = [
        {"id": "a1", "companies": ["samsung_electronics"]},
        {"id": "a2", "companies": ["samsung_electronics", "tsmc"]},
    ]
    grouped = radar_weekly.group_articles_by_company(articles, ["samsung_electronics", "tsmc"])
    assert [a["id"] for a in grouped["samsung_electronics"]] == ["a1", "a2"]
    assert [a["id"] for a in grouped["tsmc"]] == ["a2"]


def test_pick_top_issues_ranks_by_related_article_count():
    issues = [
        {
            "issue_id": "i1", "entity": "SK하이닉스", "title": "HBM4 이슈",
            "last_updated": "2026-07-08", "related_article_ids": ["a", "b", "c"],
        },
        {
            "issue_id": "i2", "entity": "삼성전자", "title": "파운드리 이슈",
            "last_updated": "2026-07-07", "related_article_ids": ["a"],
        },
    ]
    top = radar_weekly.pick_top_issues(issues, "2026-07-09", limit=3)
    assert top == ["[SK하이닉스] HBM4 이슈", "[삼성전자] 파운드리 이슈"]


def test_pick_top_issues_excludes_stale_issues():
    issues = [
        {
            "issue_id": "i1", "entity": "SK하이닉스", "title": "오래된 이슈",
            "last_updated": "2026-06-01", "related_article_ids": ["a", "b", "c"],
        },
    ]
    top = radar_weekly.pick_top_issues(issues, "2026-07-09", limit=3)
    assert top == []


def test_pick_top_issues_limits_to_n():
    issues = [
        {
            "issue_id": f"i{n}", "entity": "E", "title": f"이슈{n}",
            "last_updated": "2026-07-09", "related_article_ids": ["a"] * n,
        }
        for n in range(1, 6)
    ]
    top = radar_weekly.pick_top_issues(issues, "2026-07-09", limit=3)
    assert len(top) == 3
    assert top[0] == "[E] 이슈5"


def test_pick_top_issues_excludes_issue_missing_last_updated():
    issues = [
        {
            "issue_id": "i1", "entity": "SK하이닉스", "title": "필드 누락 이슈",
            "related_article_ids": ["a", "b", "c"],
        },
    ]
    top = radar_weekly.pick_top_issues(issues, "2026-07-09", limit=3)
    assert top == []


@patch("src.radar_weekly.gemini_client.call_gemini")
def test_classify_tone_calls_gemini_for_mentioned_companies(mock_call):
    mock_call.return_value = {
        "tone": [{"company": "samsung_electronics", "pos": 0.5, "neg": 0.2, "neu": 0.3}]
    }
    grouped = {"samsung_electronics": [{"title": "삼성전자 실적 호조"}], "tsmc": []}

    tone = radar_weekly.classify_tone(grouped)

    assert tone["samsung_electronics"] == {"pos": 0.5, "neg": 0.2, "neu": 0.3}
    assert tone["tsmc"] == {"pos": 0.0, "neg": 0.0, "neu": 1.0}
    mock_call.assert_called_once()


def test_classify_tone_skips_gemini_when_no_companies_mentioned():
    grouped = {"samsung_electronics": [], "tsmc": []}
    tone = radar_weekly.classify_tone(grouped)
    assert tone == {
        "samsung_electronics": {"pos": 0.0, "neg": 0.0, "neu": 1.0},
        "tsmc": {"pos": 0.0, "neg": 0.0, "neu": 1.0},
    }


@patch("src.radar_weekly.gemini_client.call_gemini", side_effect=RuntimeError("API 오류"))
def test_classify_tone_falls_back_to_neutral_on_failure(mock_call):
    grouped = {"samsung_electronics": [{"title": "삼성전자 뉴스"}]}
    tone = radar_weekly.classify_tone(grouped)
    assert tone == {"samsung_electronics": {"pos": 0.0, "neg": 0.0, "neu": 1.0}}
