import json
from unittest.mock import patch

from src import step4_summarize

_SOURCE_TIERS = {
    "tier1_원출처": ["삼성전자 뉴스룸"],
    "tier2_전문지": ["디일렉"],
    "tier3_재인용": ["네이버뉴스 재배포"],
}


def _core_article(**overrides):
    article = {
        "id": "art1",
        "title": "삼성전자, HBM4 수율 개선 발표",
        "url": "https://example.com/1",
        "source": "삼성전자 뉴스룸",
        "raw_text": "삼성전자가 HBM4 공정 수율을 크게 개선했다고 발표했다.",
        "tier": "핵심",
    }
    article.update(overrides)
    return article


def test_summary_model_uses_lite_tier_for_quota():
    # 무료 할당량이 넉넉하지 않은 매일 배치라 LITE_MODEL을 쓴다 (할당량이 더 큰 티어).
    assert step4_summarize._SUMMARY_MODEL == step4_summarize.gemini_client.LITE_MODEL


@patch("src.step4_summarize.gemini_client.call_gemini")
def test_generate_summaries_returns_id_to_summary_map(mock_call):
    mock_call.return_value = {
        "summaries": [{"id": "art1", "summary": "요약1"}, {"id": "art2", "summary": "요약2"}]
    }
    articles = [_core_article(id="art1"), _core_article(id="art2", title="다른 기사")]

    result = step4_summarize.generate_summaries(articles)

    assert result == {"art1": "요약1", "art2": "요약2"}


@patch("src.step4_summarize.gemini_client.call_gemini")
def test_generate_summaries_calls_gemini_exactly_once_for_multiple_articles(mock_call):
    mock_call.return_value = {"summaries": [{"id": f"art{i}", "summary": f"요약{i}"} for i in range(5)]}
    articles = [_core_article(id=f"art{i}") for i in range(5)]

    step4_summarize.generate_summaries(articles)

    assert mock_call.call_count == 1


def test_generate_summaries_returns_empty_dict_without_calling_gemini_when_no_articles():
    with patch("src.step4_summarize.gemini_client.call_gemini") as mock_call:
        result = step4_summarize.generate_summaries([])

    mock_call.assert_not_called()
    assert result == {}


@patch("src.step4_summarize.gemini_client.call_gemini")
def test_generate_summaries_truncates_raw_text_in_payload(mock_call):
    mock_call.return_value = {"summaries": [{"id": "art1", "summary": "요약"}]}
    long_text = "가" * 5000
    article = _core_article(raw_text=long_text)

    step4_summarize.generate_summaries([article])

    prompt = mock_call.call_args[0][0]
    assert "가" * (step4_summarize._RAW_TEXT_LEN + 1) not in prompt
    assert "가" * step4_summarize._RAW_TEXT_LEN in prompt


@patch("src.step4_summarize.gemini_client.call_gemini", side_effect=RuntimeError("boom"))
def test_generate_summaries_propagates_runtime_error(mock_call):
    try:
        step4_summarize.generate_summaries([_core_article()])
        assert False, "should have raised"
    except RuntimeError:
        pass


@patch("src.step4_summarize.generate_summaries")
def test_run_applies_summary_and_tag_to_each_core_article(mock_generate, tmp_path):
    mock_generate.return_value = {"art1": "삼성전자가 HBM4 수율을 개선했다고 발표했다."}
    output_path = tmp_path / "summarized.json"

    result = step4_summarize.run([_core_article(id="art1")], _SOURCE_TIERS, str(output_path))

    assert result[0]["summary"] == "삼성전자가 HBM4 수율을 개선했다고 발표했다."
    assert result[0]["confirmation_tag"] == "[확정]"
    assert result[0]["summary_fallback"] is False
    assert json.loads(output_path.read_text(encoding="utf-8"))[0]["summary"] == result[0]["summary"]


@patch("src.step4_summarize.generate_summaries")
def test_run_calls_generate_summaries_once_for_all_core_articles(mock_generate, tmp_path):
    mock_generate.return_value = {f"art{i}": f"요약{i}" for i in range(4)}
    output_path = tmp_path / "summarized.json"
    articles = [_core_article(id=f"art{i}") for i in range(4)]

    step4_summarize.run(articles, _SOURCE_TIERS, str(output_path))

    mock_generate.assert_called_once()
    assert len(mock_generate.call_args[0][0]) == 4


@patch("src.step4_summarize.generate_summaries")
def test_run_uses_extractive_summary_when_article_missing_from_batch(mock_generate, tmp_path):
    # Gemini 응답에서 빠진 기사는 raw_text 앞 문장을 발췌 요약으로 채우고 [관측]으로 태깅한다.
    mock_generate.return_value = {"art1": "요약1"}
    output_path = tmp_path / "summarized.json"
    missing_raw = "SK하이닉스가 HBM4 양산을 시작했다고 발표했다. 두 번째 문장이다. 세 번째 문장이다. 네 번째 문장이다."
    articles = [
        _core_article(id="art1"),
        _core_article(id="art2", title="응답에 없는 기사", raw_text=missing_raw),
    ]

    result = step4_summarize.run(articles, _SOURCE_TIERS, str(output_path))

    by_id = {a["id"]: a for a in result}
    assert by_id["art1"]["summary_fallback"] is False
    assert by_id["art1"]["summary_extractive"] is False
    # art2: 발췌 요약이 채워지고 fallback이 아니며 [관측] 태그가 붙는다.
    assert by_id["art2"]["summary_fallback"] is False
    assert by_id["art2"]["summary_extractive"] is True
    assert by_id["art2"]["confirmation_tag"] == "[관측]"
    assert by_id["art2"]["summary"] is not None
    assert "SK하이닉스가 HBM4 양산을 시작했다고 발표했다." in by_id["art2"]["summary"]
    assert "네 번째 문장이다." not in by_id["art2"]["summary"]  # 앞 3문장만


@patch("src.step4_summarize.generate_summaries")
def test_run_true_fallback_only_when_no_raw_text(mock_generate, tmp_path):
    # 발췌할 raw_text조차 없으면 진짜 폴백(summary=None, summary_fallback=True)으로 남는다.
    mock_generate.return_value = {}
    output_path = tmp_path / "summarized.json"
    articles = [_core_article(id="art1", raw_text="")]

    result = step4_summarize.run(articles, _SOURCE_TIERS, str(output_path))

    assert result[0]["summary_fallback"] is True
    assert result[0]["summary"] is None
    assert result[0]["summary_extractive"] is False


@patch("src.step4_summarize.notify.notify_warning")
@patch("src.step4_summarize.generate_summaries", side_effect=RuntimeError("boom"))
def test_run_uses_extractive_summary_when_batch_call_fails(mock_generate, mock_notify, tmp_path):
    """배치 호출이 통째로 실패해도(예: Gemini 503) raw_text가 있으면 발췌 요약으로 채워
    '요약 준비 중'이 전부 뜨는 것을 막는다. 실패 알림은 여전히 보낸다."""
    output_path = tmp_path / "summarized.json"
    articles = [
        _core_article(id="art1", raw_text="첫 문장이다. 둘째 문장이다."),
        _core_article(id="art2", raw_text="다른 첫 문장이다. 다른 둘째 문장이다."),
    ]

    result = step4_summarize.run(articles, _SOURCE_TIERS, str(output_path))

    assert all(a["summary_fallback"] is False for a in result)
    assert all(a["summary_extractive"] is True for a in result)
    assert all(a["summary"] for a in result)
    assert all(a["confirmation_tag"] == "[관측]" for a in result)
    mock_notify.assert_called_once()


def test_extractive_summary_takes_leading_sentences_only():
    text = "첫째 문장이다. 둘째 문장이다. 셋째 문장이다. 넷째 문장이다."
    out = step4_summarize._extractive_summary(text, max_sentences=3)
    assert "첫째 문장이다." in out
    assert "셋째 문장이다." in out
    assert "넷째 문장이다." not in out


def test_extractive_summary_empty_for_blank_raw_text():
    assert step4_summarize._extractive_summary("") == ""
    assert step4_summarize._extractive_summary("   ") == ""


@patch("src.step4_summarize.generate_summaries")
def test_run_ignores_non_core_tier_articles(mock_generate, tmp_path):
    mock_generate.return_value = {"art1": "요약1"}
    output_path = tmp_path / "summarized.json"
    articles = [_core_article(id="art1"), _core_article(id="art2", tier="확인 필요")]

    result = step4_summarize.run(articles, _SOURCE_TIERS, str(output_path))

    assert len(result) == 1
    assert result[0]["id"] == "art1"


def test_tag_confirmation_level_tier1_always_confirmed():
    assert step4_summarize.tag_confirmation_level("알려졌다", "삼성전자 뉴스룸", _SOURCE_TIERS) == "[확정]"


def test_tag_confirmation_level_tier3_always_observed():
    assert step4_summarize.tag_confirmation_level("발표했다", "네이버뉴스 재배포", _SOURCE_TIERS) == "[관측]"
