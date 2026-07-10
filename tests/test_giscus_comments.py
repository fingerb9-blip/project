import json
from unittest.mock import Mock, patch

import pytest
import requests

from src import giscus_comments


def _page(nodes, has_next=False, end_cursor=None):
    return {
        "data": {
            "repository": {
                "discussions": {
                    "nodes": nodes,
                    "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
                }
            }
        }
    }


def _mock_response(payload, status_code=200):
    response = Mock(status_code=status_code)
    response.json.return_value = payload
    response.raise_for_status = Mock()
    return response


def test_fetch_discussion_comment_counts_parses_single_page():
    payload = _page(
        [
            {"title": "/2026-07-08.html", "comments": {"totalCount": 3}},
            {"title": "/2026-07-09.html", "comments": {"totalCount": 0}},
        ]
    )
    with patch("src.giscus_comments.requests.post", return_value=_mock_response(payload)):
        counts = giscus_comments.fetch_discussion_comment_counts("owner", "repo", "token")

    assert counts == {"/2026-07-08.html": 3, "/2026-07-09.html": 0}


def test_fetch_discussion_comment_counts_paginates():
    page1 = _page([{"title": "/2026-07-08.html", "comments": {"totalCount": 1}}], has_next=True, end_cursor="c1")
    page2 = _page([{"title": "/2026-07-09.html", "comments": {"totalCount": 2}}], has_next=False)
    with patch("src.giscus_comments.requests.post", side_effect=[_mock_response(page1), _mock_response(page2)]):
        counts = giscus_comments.fetch_discussion_comment_counts("owner", "repo", "token")

    assert counts == {"/2026-07-08.html": 1, "/2026-07-09.html": 2}


def test_fetch_discussion_comment_counts_raises_on_request_error():
    with patch("src.giscus_comments.requests.post", side_effect=requests.exceptions.ConnectionError("boom")):
        with pytest.raises(RuntimeError):
            giscus_comments.fetch_discussion_comment_counts("owner", "repo", "token")


def test_fetch_discussion_comment_counts_raises_on_graphql_errors_field():
    payload = {"errors": [{"message": "Bad credentials"}]}
    with patch("src.giscus_comments.requests.post", return_value=_mock_response(payload)):
        with pytest.raises(RuntimeError):
            giscus_comments.fetch_discussion_comment_counts("owner", "repo", "token")


def test_pathname_to_date_extracts_date_from_giscus_title():
    assert giscus_comments._pathname_to_date("/2026-07-08.html") == "2026-07-08"


def test_pathname_to_date_rejects_non_date_titles():
    assert giscus_comments._pathname_to_date("/index.html") is None
    assert giscus_comments._pathname_to_date("일반 토론 주제") is None


def test_run_saves_counts_keyed_by_date(tmp_path):
    output_path = tmp_path / "comment_counts.json"
    title_counts = {"/2026-07-08.html": 3, "/2026-07-09.html": 0, "/index.html": 5}

    with patch("src.giscus_comments.fetch_discussion_comment_counts", return_value=title_counts):
        result = giscus_comments.run(str(output_path), "owner", "repo", token="tok")

    assert result == {"2026-07-08": 3, "2026-07-09": 0}
    assert json.loads(output_path.read_text(encoding="utf-8")) == result


def test_run_skips_when_no_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    output_path = tmp_path / "comment_counts.json"

    with patch("src.giscus_comments.fetch_discussion_comment_counts") as mock_fetch:
        result = giscus_comments.run(str(output_path), "owner", "repo", token=None)

    mock_fetch.assert_not_called()
    assert result == {}
    assert not output_path.exists()


def test_run_keeps_previous_data_on_failure(tmp_path):
    output_path = tmp_path / "comment_counts.json"
    output_path.write_text(json.dumps({"2026-07-08": 1}), encoding="utf-8")

    with patch("src.giscus_comments.fetch_discussion_comment_counts", side_effect=RuntimeError("boom")):
        result = giscus_comments.run(str(output_path), "owner", "repo", token="tok")

    assert result == {"2026-07-08": 1}
