import json
from unittest.mock import patch

from src import step4_5_issue_match as issue_match

_ALIASES_CONFIG = {
    "sk_hynix": {"aliases": ["SK하이닉스", "SK Hynix"], "segment": ["메모리", "HBM"]},
}


def _summarized_article(**overrides):
    article = {
        "id": "art1",
        "title": "SK하이닉스 청주 M15X 증설 착공",
        "url": "https://example.com/1",
        "source": "디일렉",
        "companies": ["sk_hynix"],
        "summary": "SK하이닉스가 청주 M15X 공장 증설에 착공했다.",
    }
    article.update(overrides)
    return article


def test_progress_summary_model_uses_lite_tier_for_quota():
    # 무료 할당량이 넉넉하지 않아 LITE_MODEL을 쓴다 (할당량이 더 큰 티어).
    assert issue_match._PROGRESS_SUMMARY_MODEL == issue_match.gemini_client.LITE_MODEL


def test_create_issue_uses_first_company_as_entity():
    article = _summarized_article()
    issue = issue_match.create_issue(article, "2026-07-08", _ALIASES_CONFIG)

    assert issue["entity"] == "SK하이닉스"
    assert issue["title"] == article["title"]
    assert issue["first_seen"] == "2026-07-08"
    assert issue["last_updated"] == "2026-07-08"
    assert issue["status"] == "진행중"
    assert issue["related_article_ids"] == ["art1"]


def test_create_issue_uses_미상_when_no_company_matched():
    article = _summarized_article(companies=[])
    issue = issue_match.create_issue(article, "2026-07-08", _ALIASES_CONFIG)

    assert issue["entity"] == "미상"


def test_apply_match_appends_article_and_updates_last_updated():
    issue = {"issue_id": "x", "related_article_ids": ["art0"], "last_updated": "2026-07-05"}
    issue_match.apply_match(issue, _summarized_article(id="art1"), "2026-07-08")

    assert issue["related_article_ids"] == ["art0", "art1"]
    assert issue["last_updated"] == "2026-07-08"


def test_apply_match_does_not_duplicate_article_id():
    issue = {"issue_id": "x", "related_article_ids": ["art1"], "last_updated": "2026-07-05"}
    issue_match.apply_match(issue, _summarized_article(id="art1"), "2026-07-08")

    assert issue["related_article_ids"] == ["art1"]


def test_days_active_computes_calendar_days():
    issue = {"first_seen": "2026-07-05"}
    assert issue_match.days_active(issue, "2026-07-08") == 3


def test_needs_progress_summary_true_after_three_days():
    issue = {"first_seen": "2026-07-05"}
    assert issue_match.needs_progress_summary(issue, "2026-07-08") is True


def test_needs_progress_summary_false_before_three_days():
    issue = {"first_seen": "2026-07-07"}
    assert issue_match.needs_progress_summary(issue, "2026-07-08") is False


def test_close_stale_issues_closes_after_seven_days_without_update():
    issues = [{"issue_id": "x", "status": "진행중", "last_updated": "2026-07-01"}]
    issue_match.close_stale_issues(issues, "2026-07-08")
    assert issues[0]["status"] == "종료"


def test_close_stale_issues_keeps_recent_issue_open():
    issues = [{"issue_id": "x", "status": "진행중", "last_updated": "2026-07-06"}]
    issue_match.close_stale_issues(issues, "2026-07-08")
    assert issues[0]["status"] == "진행중"


def test_close_stale_issues_ignores_already_closed_issue():
    issues = [{"issue_id": "x", "status": "종료", "last_updated": "2026-06-01"}]
    issue_match.close_stale_issues(issues, "2026-07-08")
    assert issues[0]["status"] == "종료"


@patch("src.step4_5_issue_match.gemini_client.call_gemini")
def test_match_articles_to_issues_returns_gemini_result(mock_call):
    mock_call.return_value = {"matches": [{"article_id": "art1", "issue_id": "issue-x"}]}
    active_issues = [{"issue_id": "issue-x", "entity": "SK하이닉스", "title": "청주 증설 이슈"}]

    result = issue_match.match_articles_to_issues([_summarized_article()], active_issues)

    assert result == {"art1": "issue-x"}


@patch("src.step4_5_issue_match.gemini_client.call_gemini")
def test_match_articles_to_issues_treats_empty_string_as_no_match(mock_call):
    mock_call.return_value = {"matches": [{"article_id": "art1", "issue_id": ""}]}
    active_issues = [{"issue_id": "issue-x", "entity": "SK하이닉스", "title": "청주 증설 이슈"}]

    result = issue_match.match_articles_to_issues([_summarized_article()], active_issues)

    assert result == {"art1": None}


def test_match_articles_to_issues_skips_gemini_when_no_active_issues():
    with patch("src.step4_5_issue_match.gemini_client.call_gemini") as mock_call:
        result = issue_match.match_articles_to_issues([_summarized_article()], [])

    mock_call.assert_not_called()
    assert result == {"art1": None}


@patch("src.step4_5_issue_match.gemini_client.call_gemini", side_effect=RuntimeError("boom"))
def test_match_articles_to_issues_fails_safe_to_no_match(mock_call):
    active_issues = [{"issue_id": "issue-x", "entity": "SK하이닉스", "title": "청주 증설 이슈"}]

    result = issue_match.match_articles_to_issues([_summarized_article()], active_issues)

    assert result == {"art1": None}


@patch("src.step4_5_issue_match.gemini_client.call_gemini")
def test_generate_progress_summary_returns_gemini_result(mock_call):
    mock_call.return_value = {"progress_summary": "3일간 이어지는 증설 이슈입니다."}
    issue = {"entity": "SK하이닉스", "title": "청주 증설 이슈", "first_seen": "2026-07-05", "last_updated": "2026-07-08"}

    result = issue_match.generate_progress_summary(issue, [_summarized_article()])

    assert result == "3일간 이어지는 증설 이슈입니다."


@patch("src.step4_5_issue_match.gemini_client.call_gemini", side_effect=RuntimeError("boom"))
def test_generate_progress_summary_keeps_previous_on_failure(mock_call):
    issue = {"progress_summary": "이전 요약"}
    result = issue_match.generate_progress_summary(issue, [_summarized_article()])

    assert result == "이전 요약"


@patch("src.step4_5_issue_match.generate_progress_summary")
@patch("src.step4_5_issue_match.match_articles_to_issues")
def test_run_creates_new_issue_when_no_match(mock_match, mock_summary, tmp_path):
    mock_match.return_value = {"art1": None}
    issues_path = tmp_path / "issues.json"

    active = issue_match.run([_summarized_article()], _ALIASES_CONFIG, issues_path, "2026-07-08")

    assert len(active) == 1
    assert active[0]["entity"] == "SK하이닉스"
    mock_summary.assert_not_called()

    saved = json.loads(issues_path.read_text(encoding="utf-8"))
    assert saved[0]["related_article_ids"] == ["art1"]


@patch("src.step4_5_issue_match.generate_progress_summary")
@patch("src.step4_5_issue_match.match_articles_to_issues")
def test_run_updates_existing_issue_on_match(mock_match, mock_summary, tmp_path):
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(
        json.dumps(
            [
                {
                    "issue_id": "issue-x",
                    "entity": "SK하이닉스",
                    "title": "청주 증설 이슈",
                    "first_seen": "2026-07-07",
                    "last_updated": "2026-07-07",
                    "status": "진행중",
                    "related_article_ids": ["art0"],
                }
            ]
        ),
        encoding="utf-8",
    )
    mock_match.return_value = {"art1": "issue-x"}

    active = issue_match.run([_summarized_article()], _ALIASES_CONFIG, issues_path, "2026-07-08")

    assert len(active) == 1
    assert active[0]["related_article_ids"] == ["art0", "art1"]
    assert active[0]["last_updated"] == "2026-07-08"
    mock_summary.assert_not_called()  # first_seen 7/7 -> today 7/8 은 아직 3일 미만


@patch("src.step4_5_issue_match.generate_progress_summary", return_value="경과 요약 문단")
@patch("src.step4_5_issue_match.match_articles_to_issues")
def test_run_generates_progress_summary_after_three_days(mock_match, mock_summary, tmp_path):
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(
        json.dumps(
            [
                {
                    "issue_id": "issue-x",
                    "entity": "SK하이닉스",
                    "title": "청주 증설 이슈",
                    "first_seen": "2026-07-05",
                    "last_updated": "2026-07-07",
                    "status": "진행중",
                    "related_article_ids": ["art0"],
                }
            ]
        ),
        encoding="utf-8",
    )
    mock_match.return_value = {"art1": "issue-x"}

    active = issue_match.run([_summarized_article()], _ALIASES_CONFIG, issues_path, "2026-07-08")

    assert active[0]["progress_summary"] == "경과 요약 문단"
    mock_summary.assert_called_once()


@patch("src.step4_5_issue_match.generate_progress_summary")
@patch("src.step4_5_issue_match.match_articles_to_issues")
def test_run_closes_stale_issue_not_matched_today(mock_match, mock_summary, tmp_path):
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(
        json.dumps(
            [
                {
                    "issue_id": "issue-old",
                    "entity": "삼성전자",
                    "title": "오래된 이슈",
                    "first_seen": "2026-06-01",
                    "last_updated": "2026-06-30",
                    "status": "진행중",
                    "related_article_ids": ["art9"],
                }
            ]
        ),
        encoding="utf-8",
    )
    mock_match.return_value = {"art1": None}

    active = issue_match.run([_summarized_article()], _ALIASES_CONFIG, issues_path, "2026-07-08")

    issue_ids = {i["issue_id"] for i in active}
    assert "issue-old" not in issue_ids

    saved = json.loads(issues_path.read_text(encoding="utf-8"))
    old_issue = next(i for i in saved if i["issue_id"] == "issue-old")
    assert old_issue["status"] == "종료"
