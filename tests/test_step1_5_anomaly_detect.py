import json
from unittest.mock import patch

from src import step1_5_anomaly_detect as anomaly

_ALIASES_CONFIG = {
    "sk_hynix": {"aliases": ["SK하이닉스", "SK Hynix"], "segment": ["메모리", "HBM"]},
}


def test_match_risk_keywords_finds_matching_keyword():
    result = anomaly.match_risk_keywords("삼성전자 공장 화재 발생", ["규제", "화재", "셧다운"])
    assert result == ["화재"]


def test_match_risk_keywords_returns_empty_when_no_match():
    result = anomaly.match_risk_keywords("삼성전자 실적 발표", ["규제", "화재", "셧다운"])
    assert result == []


def test_count_entity_keyword_mentions_counts_per_entity_and_keyword():
    articles = [
        {"companies": ["sk_hynix"], "title": "SK하이닉스 청주공장 화재", "raw_text": ""},
        {"companies": ["sk_hynix"], "title": "SK하이닉스 화재 진화", "raw_text": ""},
        {"companies": ["samsung_electronics"], "title": "삼성전자 실적 발표", "raw_text": ""},
    ]
    counts = anomaly.count_entity_keyword_mentions(articles, ["규제", "화재"])
    assert counts == {"sk_hynix": {"화재": 2}}


def test_get_baseline_avg_returns_zero_when_missing():
    assert anomaly.get_baseline_avg({}, "sk_hynix", "화재", 7) == 0.0


def test_get_baseline_avg_returns_stored_value():
    baseline = {"sk_hynix": {"화재": {"hourly_avg_7d": [0.0] * 7 + [3.5] + [0.0] * 16}}}
    assert anomaly.get_baseline_avg(baseline, "sk_hynix", "화재", 7) == 3.5


def test_update_baseline_avg_moves_toward_new_count():
    baseline = {}
    anomaly.update_baseline_avg(baseline, "sk_hynix", "화재", 7, 7)
    assert anomaly.get_baseline_avg(baseline, "sk_hynix", "화재", 7) == 1.0


def test_update_baseline_avg_keeps_other_hours_untouched():
    baseline = {}
    anomaly.update_baseline_avg(baseline, "sk_hynix", "화재", 7, 7)
    anomaly.update_baseline_avg(baseline, "sk_hynix", "화재", 8, 0)
    assert anomaly.get_baseline_avg(baseline, "sk_hynix", "화재", 7) == 1.0
    assert anomaly.get_baseline_avg(baseline, "sk_hynix", "화재", 8) == 0.0


def test_detect_anomalies_flags_ratio_over_threshold():
    counts = {"sk_hynix": {"화재": 12}}
    baseline = {"sk_hynix": {"화재": {"hourly_avg_7d": [3.0] * 24}}}
    anomalies = anomaly.detect_anomalies(counts, baseline, hour=7)
    assert anomalies == [{"entity": "sk_hynix", "keyword": "화재", "count": 12, "avg": 3.0, "ratio": 4.0}]


def test_detect_anomalies_ignores_ratio_under_threshold():
    counts = {"sk_hynix": {"화재": 5}}
    baseline = {"sk_hynix": {"화재": {"hourly_avg_7d": [3.0] * 24}}}
    assert anomaly.detect_anomalies(counts, baseline, hour=7) == []


def test_detect_anomalies_uses_min_count_when_no_baseline_cold_start():
    counts = {"sk_hynix": {"화재": 3}}
    baseline = {}
    anomalies = anomaly.detect_anomalies(counts, baseline, hour=7)
    assert len(anomalies) == 1
    assert anomalies[0]["entity"] == "sk_hynix"


def test_detect_anomalies_suppresses_low_count_cold_start():
    counts = {"sk_hynix": {"화재": 1}}
    baseline = {}
    assert anomaly.detect_anomalies(counts, baseline, hour=7) == []


def test_make_anomaly_issue_id_is_stable_for_same_entity_keyword_day():
    id1 = anomaly.make_anomaly_issue_id("sk_hynix", "화재", "2026-07-08")
    id2 = anomaly.make_anomaly_issue_id("sk_hynix", "화재", "2026-07-08")
    assert id1 == id2


def test_make_anomaly_issue_id_differs_for_different_entity():
    id1 = anomaly.make_anomaly_issue_id("sk_hynix", "화재", "2026-07-08")
    id2 = anomaly.make_anomaly_issue_id("samsung_electronics", "화재", "2026-07-08")
    assert id1 != id2


def test_is_suppressed_true_within_24h():
    issues = [{"issue_id": "abc", "last_alerted_at": "2026-07-08T06:00:00+00:00"}]
    assert anomaly.is_suppressed(issues, "abc", now_iso="2026-07-08T10:00:00+00:00") is True


def test_is_suppressed_false_after_24h():
    issues = [{"issue_id": "abc", "last_alerted_at": "2026-07-06T06:00:00+00:00"}]
    assert anomaly.is_suppressed(issues, "abc", now_iso="2026-07-08T10:00:00+00:00") is False


def test_is_suppressed_false_when_issue_not_found():
    assert anomaly.is_suppressed([], "abc", now_iso="2026-07-08T10:00:00+00:00") is False


@patch("src.step1_5_anomaly_detect.gemini_client.call_gemini")
def test_confirm_breaking_news_returns_gemini_result(mock_call):
    mock_call.return_value = {"is_breaking": True, "tag": "[확정]", "headline": "SK하이닉스 청주공장 화재"}

    result = anomaly.confirm_breaking_news(
        "sk_hynix", "화재", [{"title": "SK하이닉스 청주공장 화재", "raw_text": "..."}]
    )

    assert result == {"is_breaking": True, "tag": "[확정]", "headline": "SK하이닉스 청주공장 화재"}


@patch("src.step1_5_anomaly_detect.gemini_client.call_gemini", side_effect=RuntimeError("boom"))
def test_confirm_breaking_news_fails_safe_when_gemini_errors(mock_call):
    result = anomaly.confirm_breaking_news("sk_hynix", "화재", [{"title": "t", "raw_text": ""}])

    assert result["is_breaking"] is False


def _hourly_articles():
    return [
        {"id": "a1", "title": "SK하이닉스 청주공장 화재 발생", "raw_text": "", "source": "디일렉"},
        {"id": "a2", "title": "SK하이닉스 화재 진화 완료", "raw_text": "", "source": "디일렉"},
        {"id": "a3", "title": "SK하이닉스 청주 화재 관련 3보", "raw_text": "", "source": "디일렉"},
    ]


def _run_kwargs(tmp_path, **overrides):
    kwargs = dict(
        feeds_config={"feeds": []},
        aliases_config=_ALIASES_CONFIG,
        risk_keywords=["규제", "화재", "셧다운", "리콜"],
        frequency_baseline_path=tmp_path / "frequency_baseline.json",
        issues_path=tmp_path / "issues.json",
        dashboard_dir=tmp_path / "dashboard",
        state_path=tmp_path / "run_status.json",
        today="2026-07-08",
        hour=7,
        now_iso="2026-07-08T07:00:00+00:00",
    )
    kwargs.update(overrides)
    return kwargs


@patch("src.step1_5_anomaly_detect.confirm_breaking_news")
@patch("src.step1_5_anomaly_detect.step2_dedup.normalize_company_names")
@patch("src.step1_5_anomaly_detect.step1_collect.fetch_rss_articles")
def test_run_confirms_alert_and_updates_dashboard(mock_fetch, mock_normalize, mock_confirm, tmp_path):
    articles = _hourly_articles()
    mock_fetch.return_value = articles
    for a in articles:
        a["companies"] = ["sk_hynix"]
    mock_normalize.return_value = articles
    mock_confirm.return_value = {"is_breaking": True, "tag": "[확정]", "headline": "SK하이닉스 청주공장 화재 속보"}

    kwargs = _run_kwargs(tmp_path)
    kwargs["dashboard_dir"].mkdir()
    alerts = anomaly.run(**kwargs)

    assert len(alerts) == 1
    assert alerts[0]["entity"] == "SK하이닉스"

    issues = json.loads(kwargs["issues_path"].read_text(encoding="utf-8"))
    assert issues[0]["status"] == "진행중"
    assert issues[0]["last_alerted_at"] == "2026-07-08T07:00:00+00:00"

    index_html = (kwargs["dashboard_dir"] / "index.html").read_text(encoding="utf-8")
    assert "SK하이닉스 청주공장 화재 속보" in index_html

    alert_page = kwargs["dashboard_dir"] / "alerts" / f"{issues[0]['issue_id']}.html"
    assert alert_page.exists()

    baseline = json.loads(kwargs["frequency_baseline_path"].read_text(encoding="utf-8"))
    assert baseline["sk_hynix"]["화재"]["hourly_avg_7d"][7] > 0


@patch("src.step1_5_anomaly_detect.confirm_breaking_news")
@patch("src.step1_5_anomaly_detect.step2_dedup.normalize_company_names")
@patch("src.step1_5_anomaly_detect.step1_collect.fetch_rss_articles")
def test_run_includes_radar_section_when_alert_fires(mock_fetch, mock_normalize, mock_confirm, tmp_path):
    articles = _hourly_articles()
    mock_fetch.return_value = articles
    for a in articles:
        a["companies"] = ["sk_hynix"]
    mock_normalize.return_value = articles
    mock_confirm.return_value = {
        "is_breaking": True, "tag": "[확정]", "headline": "SK하이닉스 청주공장 화재 속보"
    }

    radar_dir = tmp_path / "radar"
    radar_dir.mkdir()
    (radar_dir / "weekly-2026-W28.json").write_text(
        json.dumps(
            {
                "week": "2026-W28",
                "mentions": {"삼성전자": 1},
                "tone": {},
                "top_issues": [],
                "commentary": "해설",
            }
        ),
        encoding="utf-8",
    )

    kwargs = _run_kwargs(tmp_path)
    kwargs["dashboard_dir"].mkdir()
    anomaly.run(**kwargs)

    index_html = (kwargs["dashboard_dir"] / "index.html").read_text(encoding="utf-8")
    assert "2026-W28" in index_html


@patch("src.step1_5_anomaly_detect.confirm_breaking_news")
@patch("src.step1_5_anomaly_detect.step2_dedup.normalize_company_names")
@patch("src.step1_5_anomaly_detect.step1_collect.fetch_rss_articles")
def test_run_keeps_pending_keywords_section_when_alert_fires(mock_fetch, mock_normalize, mock_confirm, tmp_path):
    """Finding 2: 매시 이상 신호 감지가 index.html을 재생성할 때도 피드백 키워드
    후보 섹션(config/keywords_pending.yaml)이 사라지면 안 된다.
    """
    articles = _hourly_articles()
    mock_fetch.return_value = articles
    for a in articles:
        a["companies"] = ["sk_hynix"]
    mock_normalize.return_value = articles
    mock_confirm.return_value = {"is_breaking": True, "tag": "[확정]", "headline": "SK하이닉스 청주공장 화재 속보"}

    # base_dir/data/state/issues.json 구조를 그대로 재현해 pending_path 역산이 맞는지 검증한다.
    base_dir = tmp_path
    state_dir = base_dir / "data" / "state"
    state_dir.mkdir(parents=True)
    config_dir = base_dir / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "keywords_pending.yaml").write_text(
        "candidates:\n  - keyword: 테마주\n    report_count: 2\n"
        "    last_flagged_at: '2026-07-09T00:00:00+00:00'\n    priority: false\n",
        encoding="utf-8",
    )

    kwargs = _run_kwargs(
        tmp_path,
        issues_path=state_dir / "issues.json",
        frequency_baseline_path=state_dir / "frequency_baseline.json",
        state_path=state_dir / "run_status.json",
        dashboard_dir=base_dir / "data" / "dashboard",
    )
    kwargs["dashboard_dir"].mkdir(parents=True)
    anomaly.run(**kwargs)

    index_html = (kwargs["dashboard_dir"] / "index.html").read_text(encoding="utf-8")
    assert "테마주" in index_html


@patch("src.step1_5_anomaly_detect.confirm_breaking_news")
@patch("src.step1_5_anomaly_detect.step2_dedup.normalize_company_names")
@patch("src.step1_5_anomaly_detect.step1_collect.fetch_rss_articles")
def test_run_keeps_mention_trend_section_when_alert_fires(mock_fetch, mock_normalize, mock_confirm, tmp_path):
    """Finding 3: 매시 이상 신호 감지가 index.html을 재생성할 때도 기업·기술 키워드
    언급량 트렌드 섹션(data/trends/*.json)이 사라지면 안 된다.
    """
    articles = _hourly_articles()
    mock_fetch.return_value = articles
    for a in articles:
        a["companies"] = ["sk_hynix"]
    mock_normalize.return_value = articles
    mock_confirm.return_value = {"is_breaking": True, "tag": "[확정]", "headline": "SK하이닉스 청주공장 화재 속보"}

    trends_dir = tmp_path / "trends"
    trends_dir.mkdir()
    (trends_dir / "2026-07-08.json").write_text(
        json.dumps(
            {
                "date": "2026-07-08",
                "companies": [{"name": "삼성전자", "count": 5, "is_spike": True}],
                "keywords": [{"name": "HBM", "count": 3, "is_spike": False}],
            }
        ),
        encoding="utf-8",
    )

    kwargs = _run_kwargs(tmp_path)
    kwargs["dashboard_dir"].mkdir()
    anomaly.run(**kwargs)

    index_html = (kwargs["dashboard_dir"] / "index.html").read_text(encoding="utf-8")
    assert "삼성전자" in index_html


@patch("src.step1_5_anomaly_detect.confirm_breaking_news")
@patch("src.step1_5_anomaly_detect.step2_dedup.normalize_company_names")
@patch("src.step1_5_anomaly_detect.step1_collect.fetch_rss_articles")
def test_run_hides_mention_trend_during_cold_start_hidden_stage(mock_fetch, mock_normalize, mock_confirm, tmp_path):
    """When accumulated_days < 14 (cold-start 'hidden' stage), the mention trend
    section should NOT be rendered in index.html, matching daily pipeline behavior.
    """
    articles = _hourly_articles()
    mock_fetch.return_value = articles
    for a in articles:
        a["companies"] = ["sk_hynix"]
    mock_normalize.return_value = articles
    mock_confirm.return_value = {"is_breaking": True, "tag": "[확정]", "headline": "SK하이닉스 청주공장 화재 속보"}

    # Create only 1 trend file (< 14 days = hidden stage)
    trends_dir = tmp_path / "trends"
    trends_dir.mkdir()
    (trends_dir / "2026-07-08.json").write_text(
        json.dumps(
            {
                "date": "2026-07-08",
                "companies": [{"name": "삼성전자_trend", "count": 5, "is_spike": True}],
                "keywords": [{"name": "HBM_trend", "count": 3, "is_spike": False}],
            }
        ),
        encoding="utf-8",
    )

    kwargs = _run_kwargs(tmp_path)
    kwargs["dashboard_dir"].mkdir()
    anomaly.run(**kwargs)

    index_html = (kwargs["dashboard_dir"] / "index.html").read_text(encoding="utf-8")
    # Hidden stage nulls out trend_data, so trend content should NOT appear
    assert "삼성전자_trend" not in index_html
    assert "HBM_trend" not in index_html


@patch("src.step1_5_anomaly_detect.confirm_breaking_news")
@patch("src.step1_5_anomaly_detect.step2_dedup.normalize_company_names")
@patch("src.step1_5_anomaly_detect.step1_collect.fetch_rss_articles")
def test_run_skips_gemini_call_when_suppressed(mock_fetch, mock_normalize, mock_confirm, tmp_path):
    articles = _hourly_articles()
    mock_fetch.return_value = articles
    for a in articles:
        a["companies"] = ["sk_hynix"]
    mock_normalize.return_value = articles

    issue_id = anomaly.make_anomaly_issue_id("sk_hynix", "화재", "2026-07-08")
    kwargs = _run_kwargs(tmp_path)
    kwargs["dashboard_dir"].mkdir()
    kwargs["issues_path"].write_text(
        json.dumps(
            [{"issue_id": issue_id, "status": "진행중", "last_alerted_at": "2026-07-08T06:00:00+00:00"}]
        ),
        encoding="utf-8",
    )

    alerts = anomaly.run(**kwargs)

    assert alerts == []
    mock_confirm.assert_not_called()


@patch("src.step1_5_anomaly_detect.step2_dedup.normalize_company_names")
@patch("src.step1_5_anomaly_detect.step1_collect.fetch_rss_articles")
def test_run_updates_baseline_without_dashboard_when_no_anomaly(mock_fetch, mock_normalize, tmp_path):
    articles = [{"id": "a1", "title": "SK하이닉스 실적 발표", "raw_text": "", "source": "디일렉"}]
    mock_fetch.return_value = articles
    mock_normalize.return_value = articles

    kwargs = _run_kwargs(tmp_path)
    kwargs["dashboard_dir"].mkdir()
    alerts = anomaly.run(**kwargs)

    assert alerts == []
    assert not (kwargs["dashboard_dir"] / "index.html").exists()
