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
        "source": "테스트소스",
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


def test_build_dashboard_html_renders_category_section():
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


def test_build_dashboard_html_escapes_quote_breakout_in_url():
    """Verify that quote-breakout attacks in URLs are properly escaped.

    A malicious URL like https://example.com/"onmouseover="alert(1)
    should have its quote escaped to &quot; so it cannot break out of
    the href attribute and inject an event handler.
    """
    malicious_url = 'https://example.com/"onmouseover="alert(1)'
    article = _sample_article(url=malicious_url)
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")

    # The unescaped payload should NOT appear in the output
    assert 'onmouseover="alert(1)' not in html_out
    # The escaped quote should appear in the output
    assert "&quot;" in html_out


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


def test_build_index_html_shows_success_badge(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text(
        '{"last_run_status": "success", "last_success_at": "2026-07-08T08:12:00+09:00"}',
        encoding="utf-8",
    )

    html_out = step5_assemble.build_index_html(dashboard_dir, state_path)

    assert "badge ok" in html_out
    assert "2026-07-08T08:12:00+09:00" in html_out


def test_build_index_html_shows_failure_badge(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "failed"}', encoding="utf-8")

    html_out = step5_assemble.build_index_html(dashboard_dir, state_path)

    assert "badge fail" in html_out


def test_build_index_html_handles_no_dashboards(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()

    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")

    assert "아직 생성된 브리핑이 없습니다" in html_out


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
