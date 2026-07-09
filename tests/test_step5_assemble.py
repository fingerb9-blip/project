import json

from src import step5_assemble


def _sample_issue(**overrides):
    issue = {
        "issue_id": "abc123",
        "entity": "SK하이닉스",
        "title": "청주 M15X 증설 관련 이슈",
        "first_seen": "2026-07-05",
        "last_updated": "2026-07-08",
        "status": "진행중",
        "related_article_ids": ["a", "b", "c"],
    }
    issue.update(overrides)
    return issue


def _sample_article(**overrides):
    article = {
        "id": "art0",
        "title": "삼성전자, 테스트 기사",
        "url": "https://example.com/news/1",
        "source": "디일렉",
        "summary": "테스트 요약 문장입니다.",
        "confirmation_tag": "[확정]",
        "summary_fallback": False,
        "category": ["메모리"],
    }
    article.update(overrides)
    return article


def test_build_dashboard_html_escapes_article_title():
    malicious = _sample_article(title="<script>alert(1)</script>")
    html_out = step5_assemble.build_dashboard_html([malicious], [], {}, "2026-07-08")
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out


def test_build_dashboard_html_drops_javascript_url():
    malicious = _sample_article(url="javascript:alert(1)")
    html_out = step5_assemble.build_dashboard_html([malicious], [], {}, "2026-07-08")
    assert "javascript:alert(1)" not in html_out


def test_build_dashboard_html_keeps_safe_https_url():
    article = _sample_article(url="https://example.com/article")
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'href="https://example.com/article"' in html_out


def test_build_dashboard_html_includes_summary_and_tag():
    article = _sample_article()
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert "테스트 요약 문장입니다." in html_out
    assert "[확정]" in html_out


def test_build_dashboard_html_renders_category_chips():
    article = _sample_article(category=["메모리", "파운드리"])
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert "메모리" in html_out
    assert "파운드리" in html_out


def test_build_dashboard_html_renders_pending_review():
    pending = _sample_article(title="확인 필요 기사")
    html_out = step5_assemble.build_dashboard_html([], [pending], {}, "2026-07-08")
    assert "확인 필요 기사" in html_out


def test_build_dashboard_html_flags_low_collection_count():
    stats = {"디일렉": {"today": 1, "avg7d": 10.0}}
    html_out = step5_assemble.build_dashboard_html([], [], stats, "2026-07-08")
    assert 'class="warn"' in html_out


def test_build_dashboard_html_handles_summary_fallback_article():
    fallback = _sample_article(summary_fallback=True, summary=None, confirmation_tag=None)
    html_out = step5_assemble.build_dashboard_html([fallback], [], {}, "2026-07-08")
    assert "삼성전자, 테스트 기사" in html_out
    assert "요약 없음" in html_out
    assert 'class="tag mut"' in html_out


def test_build_dashboard_html_escapes_quote_breakout_in_url():
    """Verify that quote-breakout attacks in URLs are properly escaped.

    A malicious URL like https://example.com/"onmouseover="alert(1)
    should have its quote escaped to &quot; so it cannot break out of
    the href attribute and inject an event handler.
    """
    malicious_url = 'https://example.com/"onmouseover="alert(1)'
    article = _sample_article(url=malicious_url)
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")

    assert 'onmouseover="alert(1)' not in html_out
    assert "&quot;" in html_out


def test_build_dashboard_html_confirmed_tag_uses_ok_class():
    article = _sample_article(confirmation_tag="[확정]")
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'class="tag ok"' in html_out


def test_build_dashboard_html_observed_tag_uses_obs_class():
    article = _sample_article(confirmation_tag="[관측]")
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'class="tag obs"' in html_out


def test_build_dashboard_html_maps_known_source_to_badge_class():
    article = _sample_article(source="디일렉")
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'class="badge s-thelec"' in html_out


def test_build_dashboard_html_unknown_source_falls_back_to_plain_badge():
    article = _sample_article(source="처음보는매체")
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'class="badge ">처음보는매체' in html_out


def test_build_dashboard_html_card_carries_space_separated_categories():
    article = _sample_article(category=["메모리", "파운드리"])
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'data-categories="메모리 파운드리"' in html_out


def test_build_dashboard_html_card_carries_lowercased_search_text():
    article = _sample_article(title="HBM4 발표", source="디일렉", summary="요약본")
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'data-text="' in html_out
    assert "hbm4 발표" in html_out


def test_build_dashboard_html_includes_appbar_and_search():
    html_out = step5_assemble.build_dashboard_html([], [], {}, "2026-07-08")
    assert 'class="brand"' in html_out
    assert 'id="q"' in html_out


def test_build_dashboard_html_includes_filter_bar_for_present_categories():
    article = _sample_article(category=["메모리", "파운드리"])
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'class="filter"' in html_out
    assert 'data-cat="메모리"' in html_out
    assert 'data-cat="all"' in html_out


def test_build_dashboard_html_omits_filter_bar_when_no_categories():
    html_out = step5_assemble.build_dashboard_html([], [], {}, "2026-07-08")
    assert 'class="filter"' not in html_out


def test_build_dashboard_html_includes_site_footer():
    html_out = step5_assemble.build_dashboard_html([], [], {}, "2026-07-08")
    assert "site-footer" in html_out
    assert "디일렉" in html_out


def test_build_dashboard_html_omits_out_of_scope_features():
    """§0 스코프 밖: 조회수·알림 벨·PDF·북마크·커뮤니티는 렌더링되지 않는다."""
    article = _sample_article()
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert "조회수" not in html_out
    assert "PDF" not in html_out
    assert "북마크" not in html_out


def test_build_index_html_lists_dates_newest_first(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    for d in ("2026-07-06", "2026-07-08", "2026-07-07"):
        (dashboard_dir / f"{d}.html").write_text("<html></html>", encoding="utf-8")

    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")

    first = html_out.index("2026-07-08")
    second = html_out.index("2026-07-07")
    third = html_out.index("2026-07-06")
    assert first < second < third


def test_build_index_html_includes_latest_date_as_report_card_too(tmp_path):
    """v2는 v1과 달리 최신 날짜도 히어로 아래 리포트 카드 목록에 그대로 포함된다 (§5-1)."""
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")

    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")

    assert html_out.count("2026-07-08") >= 2  # 히어로 링크 + 리포트 카드


def test_build_index_html_shows_success_status(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text(
        '{"last_run_status": "success", "last_success_at": "2026-07-08T08:12:00+09:00"}',
        encoding="utf-8",
    )

    html_out = step5_assemble.build_index_html(dashboard_dir, state_path)

    assert "status ok" in html_out
    assert "2026-07-08T08:12:00+09:00" in html_out


def test_build_index_html_shows_failure_status(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "failed"}', encoding="utf-8")

    html_out = step5_assemble.build_index_html(dashboard_dir, state_path)

    assert "status fail" in html_out


def test_build_index_html_handles_no_dashboards(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()

    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")

    assert "아직 생성된 브리핑이 없습니다" in html_out


def test_build_index_html_renders_hero_and_report_card(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")
    state_path = tmp_path / "run_status.json"

    html_out = step5_assemble.build_index_html(dashboard_dir, state_path)

    assert 'class="hero"' in html_out
    assert 'href="2026-07-08.html"' in html_out
    assert "리포트 읽기" in html_out
    assert "2026년 7월 8일" in html_out


def test_build_index_html_omits_pdf_download_by_default(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")

    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")

    assert "PDF" not in html_out


def test_build_index_html_includes_appbar_search_and_footer(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")
    assert 'class="brand"' in html_out
    assert 'id="q"' in html_out
    assert "site-footer" in html_out


def test_run_writes_archive_dashboard_and_index(tmp_path):
    archive_path = tmp_path / "archive" / "2026-07-08.md"
    dashboard_dir = tmp_path / "dashboard"
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "success"}', encoding="utf-8")

    step5_assemble.run(
        [_sample_article()],
        [],
        {},
        str(archive_path),
        str(dashboard_dir),
        "2026-07-08",
        str(state_path),
    )

    assert archive_path.exists()
    assert (dashboard_dir / "2026-07-08.html").exists()
    assert (dashboard_dir / "index.html").exists()
    assert (dashboard_dir / "style.css").exists()


def test_run_includes_radar_section_when_provided(tmp_path):
    archive_path = tmp_path / "archive" / "2026-07-08.md"
    dashboard_dir = tmp_path / "dashboard"
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "success"}', encoding="utf-8")
    radar_data = {
        "week": "2026-W28",
        "mentions": {"삼성전자": 1},
        "tone": {},
        "top_issues": [],
        "commentary": "해설",
    }

    step5_assemble.run(
        [_sample_article()],
        [],
        {},
        str(archive_path),
        str(dashboard_dir),
        "2026-07-08",
        str(state_path),
        radar_data=radar_data,
    )

    index_html = (dashboard_dir / "index.html").read_text(encoding="utf-8")
    assert "2026-W28" in index_html
    assert "해설" in index_html


def test_build_dashboard_html_renders_active_issue_timeline():
    issue = _sample_issue()
    html_out = step5_assemble.build_dashboard_html([], [], {}, "2026-07-08", active_issues=[issue])
    assert "청주 M15X 증설 관련 이슈" in html_out
    assert "SK하이닉스" in html_out
    assert "2026-07-05" in html_out
    assert "3건" in html_out


def test_build_dashboard_html_escapes_issue_title_and_progress_summary():
    issue = _sample_issue(title="<script>alert(1)</script>", progress_summary="<b>경과</b>")
    html_out = step5_assemble.build_dashboard_html([], [], {}, "2026-07-08", active_issues=[issue])
    assert "<script>alert(1)</script>" not in html_out
    assert "<b>경과</b>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_build_dashboard_html_no_issue_section_when_no_active_issues():
    html_out = step5_assemble.build_dashboard_html([], [], {}, "2026-07-08", active_issues=[])
    assert "진행 중 이슈" not in html_out


def test_build_briefing_renders_active_issue_timeline():
    issue = _sample_issue()
    md = step5_assemble.build_briefing([], [], {}, active_issues=[issue])
    assert "진행 중 이슈" in md
    assert "청주 M15X 증설 관련 이슈" in md


def test_build_alert_banner_html_renders_alert():
    alert = {"issue_id": "abc123", "entity": "SK하이닉스", "headline": "청주공장 화재 속보", "tag": "[확정]"}
    html_out = step5_assemble.build_alert_banner_html([alert])
    assert "청주공장 화재 속보" in html_out
    assert 'href="alerts/abc123.html"' in html_out
    assert "[확정]" in html_out


def test_build_alert_banner_html_escapes_headline():
    alert = {"issue_id": "abc123", "entity": "SK하이닉스", "headline": "<script>x</script>", "tag": "[확정]"}
    html_out = step5_assemble.build_alert_banner_html([alert])
    assert "<script>x</script>" not in html_out


def test_build_alert_banner_html_empty_when_no_alerts():
    assert step5_assemble.build_alert_banner_html([]) == ""


def test_build_alert_detail_html_renders_issue_fields():
    issue = _sample_issue(progress_summary="3일간 이어지는 이슈입니다.")
    html_out = step5_assemble.build_alert_detail_html(issue)
    assert "청주 M15X 증설 관련 이슈" in html_out
    assert "SK하이닉스" in html_out
    assert "3일간 이어지는 이슈입니다." in html_out


def test_build_index_html_shows_recent_alert_banner(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "success"}', encoding="utf-8")
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(
        '[{"issue_id": "abc123", "entity": "SK하이닉스", "status": "진행중", '
        '"headline": "청주공장 화재 속보", "tag": "[확정]", '
        '"last_alerted_at": "2026-07-08T06:00:00+00:00"}]',
        encoding="utf-8",
    )

    html_out = step5_assemble.build_index_html(
        dashboard_dir, state_path, issues_path=issues_path, now="2026-07-08T07:00:00+00:00"
    )

    assert "청주공장 화재 속보" in html_out


def test_build_index_html_hides_stale_alert_banner(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "success"}', encoding="utf-8")
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(
        '[{"issue_id": "abc123", "entity": "SK하이닉스", "status": "진행중", '
        '"headline": "청주공장 화재 속보", "tag": "[확정]", '
        '"last_alerted_at": "2026-07-05T06:00:00+00:00"}]',
        encoding="utf-8",
    )

    html_out = step5_assemble.build_index_html(
        dashboard_dir, state_path, issues_path=issues_path, now="2026-07-08T07:00:00+00:00"
    )

    assert "청주공장 화재 속보" not in html_out


def test_load_latest_radar_returns_none_when_missing(tmp_path):
    assert step5_assemble.load_latest_radar(tmp_path / "radar") is None


def test_load_latest_radar_returns_most_recent_week(tmp_path):
    radar_dir = tmp_path / "radar"
    radar_dir.mkdir()
    (radar_dir / "weekly-2026-W27.json").write_text('{"week": "2026-W27"}', encoding="utf-8")
    (radar_dir / "weekly-2026-W28.json").write_text('{"week": "2026-W28"}', encoding="utf-8")

    data = step5_assemble.load_latest_radar(radar_dir)

    assert data["week"] == "2026-W28"


def test_build_radar_section_html_renders_bars_and_commentary():
    radar_data = {
        "week": "2026-W28",
        "mentions": {"삼성전자": 10, "SK하이닉스": 5},
        "tone": {"삼성전자": {"pos": 0.6, "neg": 0.1, "neu": 0.3}},
        "top_issues": ["[삼성전자] HBM4 발표"],
        "commentary": "이번 주는 HBM 경쟁이 두드러졌습니다.",
    }
    html_out = step5_assemble.build_radar_section_html(radar_data)
    assert "2026-W28" in html_out
    assert "삼성전자" in html_out
    assert "HBM4 발표" in html_out
    assert "HBM 경쟁이 두드러졌습니다" in html_out
    assert "width:100%" in html_out


def test_build_radar_section_html_empty_when_no_data():
    assert step5_assemble.build_radar_section_html(None) == ""
    assert step5_assemble.build_radar_section_html({}) == ""


def test_build_radar_section_html_escapes_company_name():
    radar_data = {
        "week": "2026-W28",
        "mentions": {"<script>x</script>": 1},
        "tone": {},
        "top_issues": [],
        "commentary": "",
    }
    html_out = step5_assemble.build_radar_section_html(radar_data)
    assert "<script>x</script>" not in html_out


def test_build_index_html_includes_radar_section(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "success"}', encoding="utf-8")
    radar_data = {
        "week": "2026-W28", "mentions": {"삼성전자": 1}, "tone": {}, "top_issues": [], "commentary": "해설",
    }

    html_out = step5_assemble.build_index_html(dashboard_dir, state_path, radar_data=radar_data)

    assert "2026-W28" in html_out
    assert "해설" in html_out


def test_build_index_html_omits_radar_section_when_none(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "success"}', encoding="utf-8")

    html_out = step5_assemble.build_index_html(dashboard_dir, state_path)

    assert "경쟁 구도 레이더" not in html_out


def test_build_dashboard_html_shows_source_type_badge():
    article = _sample_article(source_type="특허")
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'data-source-type="특허"' in html_out
    assert ">특허<" in html_out


def test_build_dashboard_html_defaults_source_type_to_news_when_missing():
    article = _sample_article()
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'data-source-type="언론"' in html_out


def test_build_dashboard_html_includes_deep_tech_filter_toggle():
    html_out = step5_assemble.build_dashboard_html([_sample_article()], [], {}, "2026-07-08")
    assert 'id="deep-tech-filter"' in html_out
    assert "학회·특허만 보기" in html_out


def test_build_dashboard_html_omits_noise_button_when_no_repo_url():
    html_out = step5_assemble.build_dashboard_html([_sample_article()], [], {}, "2026-07-08")
    assert "노이즈로 표시" not in html_out


def test_build_dashboard_html_renders_noise_button_with_repo_url():
    article = _sample_article(id="art1", url="https://example.com/a", title="테스트 기사")
    html_out = step5_assemble.build_dashboard_html(
        [article], [], {}, "2026-07-08", repo_url="https://github.com/owner/repo"
    )
    assert "노이즈로 표시" in html_out
    assert "https://github.com/owner/repo/issues/new?" in html_out
    assert "labels=noise-report" in html_out


def test_build_dashboard_html_noise_button_escapes_title_in_url():
    article = _sample_article(id="art1", url="https://example.com/a", title="<script>x</script>")
    html_out = step5_assemble.build_dashboard_html(
        [article], [], {}, "2026-07-08", repo_url="https://github.com/owner/repo"
    )
    assert "<script>x</script>" not in html_out


def test_load_pending_keywords_returns_empty_when_missing(tmp_path):
    assert step5_assemble.load_pending_keywords(tmp_path / "missing.yaml") == []


def test_load_pending_keywords_returns_candidates_when_present(tmp_path):
    pending_path = tmp_path / "keywords_pending.yaml"
    pending_path.write_text(
        "candidates:\n"
        "  - keyword: 테마주\n"
        "    report_count: 2\n"
        "    last_flagged_at: '2026-07-09T00:00:00+00:00'\n"
        "    priority: false\n",
        encoding="utf-8",
    )

    result = step5_assemble.load_pending_keywords(pending_path)

    assert result == [
        {
            "keyword": "테마주",
            "report_count": 2,
            "last_flagged_at": "2026-07-09T00:00:00+00:00",
            "priority": False,
        }
    ]


def test_build_pending_keywords_section_html_renders_candidates():
    candidates = [
        {"keyword": "테마주", "report_count": 2, "last_flagged_at": "2026-07-09T00:00:00+00:00", "priority": False}
    ]
    html_out = step5_assemble.build_pending_keywords_section_html(candidates)
    assert "테마주" in html_out
    assert ">2<" in html_out


def test_build_pending_keywords_section_html_empty_when_no_candidates():
    assert step5_assemble.build_pending_keywords_section_html([]) == ""


def test_build_pending_keywords_section_html_flags_priority_candidate():
    candidates = [
        {"keyword": "테마주", "report_count": 3, "last_flagged_at": "x", "priority": True}
    ]
    html_out = step5_assemble.build_pending_keywords_section_html(candidates)
    assert 'class="warn"' in html_out


def test_build_dashboard_html_deep_tech_filter_scoped_to_today_core_section():
    """학회·특허만 보기 필터는 '오늘의 핵심' 섹션 카드만 대상으로 해야 한다.

    '진행 중 이슈' 섹션의 카드는 data-source-type이 없어 전역 .card 셀렉터를
    쓰면 필터 체크 시 같이 숨겨진다 (Finding 1). #feed로 스코핑해야 한다 ("오늘의 핵심"
    카드만 #feed 안에 렌더링되고, 진행 중 이슈 카드는 그 밖에 렌더링된다).
    """
    issue = _sample_issue()
    html_out = step5_assemble.build_dashboard_html(
        [_sample_article()], [], {}, "2026-07-08", active_issues=[issue]
    )
    assert '<div id="feed">' in html_out
    assert "#feed .card" in html_out
    assert "document.querySelectorAll('.card')" not in html_out


def test_build_index_html_includes_pending_keywords_section(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "success"}', encoding="utf-8")
    candidates = [
        {"keyword": "테마주", "report_count": 2, "last_flagged_at": "x", "priority": False}
    ]

    html_out = step5_assemble.build_index_html(dashboard_dir, state_path, pending_keywords=candidates)

    assert "테마주" in html_out


# --- 실시간 트렌드 섹션 (실시간_트렌드_섹션_명세.md) ---


def test_compute_keyword_trends_aggregates_companies_and_topics():
    articles = [
        {"title": "삼성전자 HBM4 공개", "summary": "삼성전자가 HBM4를 공개했다"},
        {"title": "삼성전자 파운드리 증설", "summary": "삼성전자 파운드리 증설 발표"},
        {"title": "SK하이닉스 HBM 공급 확대", "summary": "SK하이닉스가 HBM을 공급한다"},
        {"title": "수출통제 이슈", "summary": "미국의 수출통제 강화"},
    ]

    trends = step5_assemble._compute_keyword_trends(articles)

    counts = {t["keyword"]: t["count"] for t in trends}
    assert counts["삼성전자"] == 2  # 기업(별칭 매칭), 같은 기사 내 중복 미집계
    assert counts["HBM"] == 2  # 토픽 키워드
    assert counts["SK하이닉스"] == 1
    assert counts["파운드리 증설"] == 1
    assert counts["수출통제"] == 1


def test_compute_keyword_trends_sorts_descending_by_count():
    articles = [
        {"title": "삼성전자", "summary": ""},
        {"title": "삼성전자", "summary": ""},
        {"title": "삼성전자", "summary": ""},
        {"title": "SK하이닉스", "summary": ""},
    ]

    trends = step5_assemble._compute_keyword_trends(articles)
    counts_in_order = [t["count"] for t in trends]

    assert counts_in_order == sorted(counts_in_order, reverse=True)
    assert trends[0]["keyword"] == "삼성전자"


def test_compute_keyword_trends_percentages_sum_to_about_100():
    articles = [
        {"title": "삼성전자", "summary": ""},
        {"title": "삼성전자", "summary": ""},
        {"title": "SK하이닉스", "summary": ""},
        {"title": "TSMC", "summary": ""},
        {"title": "인텔", "summary": ""},
        {"title": "엔비디아", "summary": ""},
        {"title": "HBM", "summary": ""},
    ]

    trends = step5_assemble._compute_keyword_trends(articles)

    assert abs(sum(t["pct"] for t in trends) - 100.0) < 1.0


def test_compute_keyword_trends_truncates_to_top_n_with_other_bucket():
    articles = [
        {"title": "삼성전자", "summary": ""},
        {"title": "삼성전자", "summary": ""},
        {"title": "SK하이닉스", "summary": ""},
        {"title": "TSMC", "summary": ""},
    ]

    trends = step5_assemble._compute_keyword_trends(articles, top_n=2)

    assert len(trends) == 3  # 상위 2개 + 기타
    assert trends[0]["keyword"] == "삼성전자"
    assert trends[-1]["keyword"] == "기타"
    assert trends[-1]["color"] == step5_assemble._TREND_OTHER_COLOR


def test_compute_keyword_trends_empty_when_no_matches():
    articles = [{"title": "관계없는 기사", "summary": "아무 키워드도 없음"}]
    assert step5_assemble._compute_keyword_trends(articles) == []


def test_compute_keyword_trends_empty_articles_returns_empty():
    assert step5_assemble._compute_keyword_trends([]) == []


def test_donut_svg_renders_circles_with_formatted_floats():
    trends = [
        {"keyword": "삼성전자", "count": 6, "pct": 60.0, "color": "#6C5CE7"},
        {"keyword": "SK하이닉스", "count": 4, "pct": 40.0, "color": "#3D6FE6"},
    ]

    svg = step5_assemble._donut_svg(trends, 10)

    assert 'role="img"' in svg
    assert svg.count("<circle") == 2
    assert ">10<" in svg  # 중앙 총 카운트
    assert "stroke-dasharray=\"169.646 113.097\"" in svg  # 60% of C≈282.743


def test_donut_svg_escapes_keyword_in_title():
    trends = [{"keyword": "<script>alert(1)</script>", "count": 1, "pct": 100.0, "color": "#000"}]

    svg = step5_assemble._donut_svg(trends, 1)

    assert "<script>alert(1)</script>" not in svg
    assert "&lt;script&gt;" in svg


def test_render_trend_section_empty_when_no_trends():
    assert step5_assemble.render_trend_section([], 0) == ""


def test_render_trend_section_renders_bars_matching_donut_colors():
    trends = [
        {"keyword": "삼성전자", "count": 6, "pct": 60.0, "color": "#6C5CE7"},
        {"keyword": "SK하이닉스", "count": 4, "pct": 40.0, "color": "#3D6FE6"},
    ]

    html_out = step5_assemble.render_trend_section(trends, 10)

    assert 'class="trend"' in html_out
    assert "최신 브리핑 기준" in html_out
    assert "background:#6C5CE7" in html_out
    assert "background:#3D6FE6" in html_out
    assert "60.0%" in html_out


def test_render_trend_section_escapes_keyword_label():
    trends = [{"keyword": "<script>alert(1)</script>", "count": 5, "pct": 100.0, "color": "#000"}]

    html_out = step5_assemble.render_trend_section(trends, 5)

    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_build_index_html_includes_trend_section_from_latest_summarized(tmp_path):
    dashboard_dir = tmp_path / "data" / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "2026-07-09.html").write_text("<html></html>", encoding="utf-8")

    summarized_dir = tmp_path / "data" / "summarized"
    summarized_dir.mkdir(parents=True)
    (summarized_dir / "2026-07-09.json").write_text(
        json.dumps(
            [
                {"title": "삼성전자 HBM4 공개", "summary": "삼성전자가 HBM4를 공개했다"},
                {"title": "SK하이닉스 HBM 공급 확대", "summary": ""},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")

    assert "실시간 트렌드" in html_out
    assert 'class="trend"' in html_out
    assert "삼성전자" in html_out


def test_build_index_html_omits_trend_section_when_no_source_data(tmp_path):
    dashboard_dir = tmp_path / "data" / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "2026-07-09.html").write_text("<html></html>", encoding="utf-8")

    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")

    assert "실시간 트렌드" not in html_out


def test_select_highlights_excludes_articles_without_summary():
    no_summary = _sample_article(id="a1", summary=None, summary_fallback=True)
    has_summary = _sample_article(id="a2", summary="요약 있음", summary_fallback=False)

    result = step5_assemble.select_highlights([no_summary, has_summary])

    assert [a["id"] for a in result] == ["a2"]


def test_select_highlights_excludes_articles_with_empty_summary_string():
    empty_summary = _sample_article(id="a1", summary="", summary_fallback=False)
    result = step5_assemble.select_highlights([empty_summary])
    assert result == []


def test_select_highlights_prefers_confirmed_over_observed():
    observed = _sample_article(
        id="a1", confirmation_tag="[관측]", category=["메모리"],
        published_at="2026-07-09T09:00:00+09:00",
    )
    confirmed = _sample_article(
        id="a2", confirmation_tag="[확정]", category=["파운드리"],
        published_at="2026-07-09T08:00:00+09:00",  # 더 오래됐지만 확정이라 우선
    )

    result = step5_assemble.select_highlights([observed, confirmed], max_count=1)

    assert [a["id"] for a in result] == ["a2"]


def test_select_highlights_maximizes_category_diversity():
    memory1 = _sample_article(
        id="a1", category=["메모리"], published_at="2026-07-09T10:00:00+09:00",
    )
    memory2 = _sample_article(
        id="a2", category=["메모리"], published_at="2026-07-09T09:00:00+09:00",
    )
    foundry = _sample_article(
        id="a3", category=["파운드리"], published_at="2026-07-09T08:00:00+09:00",
    )

    result = step5_assemble.select_highlights([memory1, memory2, foundry], max_count=2)

    assert [a["id"] for a in result] == ["a1", "a3"]  # 메모리 중복(a2)보다 다른 카테고리(a3) 우선


def test_select_highlights_backfills_with_duplicate_category_when_not_enough_diversity():
    memory1 = _sample_article(
        id="a1", category=["메모리"], published_at="2026-07-09T10:00:00+09:00",
    )
    memory2 = _sample_article(
        id="a2", category=["메모리"], published_at="2026-07-09T09:00:00+09:00",
    )

    result = step5_assemble.select_highlights([memory1, memory2], max_count=2)

    assert [a["id"] for a in result] == ["a1", "a2"]  # 카테고리가 겹쳐도 max_count까지 채움


def test_select_highlights_sorts_by_recency_within_same_confirmation_level():
    older = _sample_article(
        id="a1", category=["메모리"], published_at="2026-07-08T09:00:00+09:00",
    )
    newer = _sample_article(
        id="a2", category=["파운드리"], published_at="2026-07-09T09:00:00+09:00",
    )

    result = step5_assemble.select_highlights([older, newer])

    assert [a["id"] for a in result] == ["a2", "a1"]


def test_select_highlights_returns_fewer_than_max_count_when_not_enough_candidates():
    only_one = _sample_article(id="a1")
    result = step5_assemble.select_highlights([only_one], max_count=5)
    assert len(result) == 1


def test_select_highlights_respects_max_count_cap():
    articles = [
        _sample_article(id=f"a{i}", category=[f"cat{i}"], published_at="2026-07-09T09:00:00+09:00")
        for i in range(8)
    ]
    result = step5_assemble.select_highlights(articles, max_count=5)
    assert len(result) == 5


def test_build_dashboard_html_renders_highlight_strip():
    article = _sample_article(title="하이라이트 대상 기사")
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'class="highlight-strip"' in html_out
    assert 'class="highlight-card"' in html_out
    assert "하이라이트 대상 기사" in html_out


def test_build_dashboard_html_highlight_card_escapes_title():
    malicious = _sample_article(title="<script>alert(1)</script>")
    html_out = step5_assemble.build_dashboard_html([malicious], [], {}, "2026-07-08")
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out


def test_build_dashboard_html_highlight_card_shows_category_chip():
    article = _sample_article(category=["메모리"])
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'class="highlight-strip"' in html_out
    assert "메모리" in html_out


def test_build_dashboard_html_omits_highlight_strip_when_no_eligible_articles():
    no_summary = _sample_article(summary=None, summary_fallback=True)
    html_out = step5_assemble.build_dashboard_html([no_summary], [], {}, "2026-07-08")
    assert 'class="highlight-strip"' not in html_out


def test_build_dashboard_html_highlight_strip_appears_before_full_feed():
    article = _sample_article()
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    highlight_pos = html_out.index('class="highlight-strip"')
    feed_pos = html_out.index('id="feed"')
    assert highlight_pos < feed_pos
