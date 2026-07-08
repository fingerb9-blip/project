from src import issue_tracking


def test_load_issues_returns_empty_list_when_missing(tmp_path):
    path = tmp_path / "issues.json"

    assert issue_tracking.load_issues(path) == []


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "issues.json"
    issues = [{"issue_id": "abc123", "entity": "SK하이닉스", "status": "진행중"}]

    issue_tracking.save_issues(path, issues)

    assert issue_tracking.load_issues(path) == issues


def test_entity_display_name_returns_first_alias():
    aliases_config = {"sk_hynix": {"aliases": ["SK하이닉스", "SK Hynix"]}}
    assert issue_tracking.entity_display_name("sk_hynix", aliases_config) == "SK하이닉스"


def test_entity_display_name_falls_back_to_entity_id_when_unknown():
    assert issue_tracking.entity_display_name("unknown_co", {}) == "unknown_co"


def test_find_issue_returns_matching_issue():
    issues = [{"issue_id": "a"}, {"issue_id": "b"}]
    assert issue_tracking.find_issue(issues, "b") == {"issue_id": "b"}


def test_find_issue_returns_none_when_missing():
    assert issue_tracking.find_issue([{"issue_id": "a"}], "z") is None
