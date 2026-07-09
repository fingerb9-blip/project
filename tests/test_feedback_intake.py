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
