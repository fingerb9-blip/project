import json
from unittest.mock import patch

import pytest

from src import feedback_batch


def test_load_queue_returns_empty_when_missing(tmp_path):
    assert feedback_batch.load_queue(tmp_path / "missing.json") == []


def test_extract_common_keywords_returns_empty_for_empty_input():
    assert feedback_batch.extract_common_keywords([]) == []


@patch("src.feedback_batch.gemini_client.call_gemini")
def test_extract_common_keywords_calls_gemini_and_returns_keywords(mock_call):
    mock_call.return_value = {"keywords": ["테마주", "급등"]}
    articles = [{"title": "삼성전자 테마주 급등"}]

    result = feedback_batch.extract_common_keywords(articles)

    assert result == ["테마주", "급등"]
    mock_call.assert_called_once()


@patch("src.feedback_batch.gemini_client.call_gemini", side_effect=RuntimeError("API 오류"))
def test_extract_common_keywords_falls_back_to_titles_on_failure(mock_call):
    articles = [{"title": "제목1"}, {"title": "제목2"}]

    result = feedback_batch.extract_common_keywords(articles)

    assert result == ["제목1", "제목2"]


def test_count_keyword_matches_counts_substring_matches_in_titles():
    titles = ["삼성전자 테마주 급등", "SK하이닉스 테마주 열풍", "삼성전자 실적 발표"]
    assert feedback_batch._count_keyword_matches("테마주", titles) == 2


def test_count_keyword_matches_returns_zero_when_no_match():
    titles = ["삼성전자 실적 발표"]
    assert feedback_batch._count_keyword_matches("테마주", titles) == 0


def test_merge_candidates_adds_new_keyword():
    pending = {"candidates": []}
    result = feedback_batch.merge_candidates(pending, {"테마주": 1}, "2026-07-09T00:00:00+00:00")
    assert result["candidates"][0]["keyword"] == "테마주"
    assert result["candidates"][0]["report_count"] == 1
    assert result["candidates"][0]["priority"] is False


def test_merge_candidates_increments_existing_keyword_report_count():
    pending = {
        "candidates": [
            {
                "keyword": "테마주",
                "report_count": 1,
                "first_flagged_at": "2026-07-01T00:00:00+00:00",
                "last_flagged_at": "2026-07-01T00:00:00+00:00",
                "priority": False,
            }
        ]
    }
    result = feedback_batch.merge_candidates(pending, {"테마주": 1}, "2026-07-09T00:00:00+00:00")
    assert result["candidates"][0]["report_count"] == 2
    assert result["candidates"][0]["last_flagged_at"] == "2026-07-09T00:00:00+00:00"


def test_merge_candidates_sets_priority_at_threshold():
    pending = {
        "candidates": [
            {
                "keyword": "테마주",
                "report_count": 2,
                "first_flagged_at": "x",
                "last_flagged_at": "x",
                "priority": False,
            }
        ]
    }
    result = feedback_batch.merge_candidates(pending, {"테마주": 1}, "2026-07-09T00:00:00+00:00")
    assert result["candidates"][0]["report_count"] == 3
    assert result["candidates"][0]["priority"] is True


def test_merge_candidates_single_batch_with_three_matches_crosses_threshold_immediately():
    """Finding 3: report_count는 배치 호출 횟수가 아니라 실제 신고(매칭) 건수를 반영해야 한다.

    같은 주간 배치 안에서 키워드가 3개 기사에 매칭되면, 별도 배치를 3주 기다릴
    필요 없이 그 자리에서 priority=True가 되어야 한다.
    """
    pending = {"candidates": []}
    result = feedback_batch.merge_candidates(pending, {"테마주": 3}, "2026-07-09T00:00:00+00:00")
    assert result["candidates"][0]["report_count"] == 3
    assert result["candidates"][0]["priority"] is True


@patch("src.feedback_batch.gemini_client.call_gemini")
def test_run_clears_queue_and_writes_pending(mock_call, tmp_path):
    mock_call.return_value = {"keywords": ["테마주"]}
    queue_path = tmp_path / "feedback_queue.json"
    queue_path.write_text('[{"article_id": "a", "title": "삼성전자 테마주 급등"}]', encoding="utf-8")
    pending_path = tmp_path / "keywords_pending.yaml"

    result = feedback_batch.run(str(queue_path), str(pending_path), "2026-07-09T00:00:00+00:00")

    assert result["candidates"][0]["keyword"] == "테마주"
    assert pending_path.exists()
    assert json.loads(queue_path.read_text(encoding="utf-8")) == []


@patch("src.feedback_batch.gemini_client.call_gemini")
def test_run_counts_actual_report_volume_not_batch_presence(mock_call, tmp_path):
    """Finding 3: 같은 주간 배치에서 3개 기사가 같은 키워드로 신고되면
    report_count가 1(배치당 1회)이 아니라 3(실제 매칭 건수)이어야 한다.
    """
    mock_call.return_value = {"keywords": ["테마주"]}
    queue_path = tmp_path / "feedback_queue.json"
    queue_path.write_text(
        json.dumps(
            [
                {"article_id": "a", "title": "삼성전자 테마주 급등"},
                {"article_id": "b", "title": "SK하이닉스 테마주 열풍"},
                {"article_id": "c", "title": "테마주 관련주 폭등"},
            ]
        ),
        encoding="utf-8",
    )
    pending_path = tmp_path / "keywords_pending.yaml"

    result = feedback_batch.run(str(queue_path), str(pending_path), "2026-07-09T00:00:00+00:00")

    assert result["candidates"][0]["report_count"] == 3
    assert result["candidates"][0]["priority"] is True
