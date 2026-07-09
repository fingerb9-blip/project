import json

from src import feedback_intake


def test_parse_issue_body_extracts_fields():
    body = (
        "article_id: abc123\n"
        "url: https://example.com/a\n"
        "title: 테스트 기사 제목\n"
        "reason: noise\n"
    )
    result = feedback_intake.parse_issue_body(body)
    assert result == {
        "article_id": "abc123",
        "url": "https://example.com/a",
        "title": "테스트 기사 제목",
        "reason": "noise",
    }


def test_parse_issue_body_defaults_reason_to_noise_when_missing():
    body = "article_id: abc123\nurl: https://example.com/a\ntitle: 제목\n"
    result = feedback_intake.parse_issue_body(body)
    assert result["reason"] == "noise"


def test_parse_issue_body_handles_empty_body():
    assert feedback_intake.parse_issue_body("")["article_id"] == ""


def test_append_to_queue_creates_new_file(tmp_path):
    queue_path = tmp_path / "state" / "feedback_queue.json"
    entry = {"article_id": "abc", "flagged_at": "2026-07-09T10:00:00+09:00", "reason": "noise"}

    result = feedback_intake.append_to_queue(queue_path, entry)

    assert result == [entry]
    assert json.loads(queue_path.read_text(encoding="utf-8")) == [entry]


def test_append_to_queue_appends_to_existing_queue(tmp_path):
    queue_path = tmp_path / "feedback_queue.json"
    queue_path.write_text('[{"article_id": "first"}]', encoding="utf-8")

    result = feedback_intake.append_to_queue(queue_path, {"article_id": "second"})

    assert [e["article_id"] for e in result] == ["first", "second"]
