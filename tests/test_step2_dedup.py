from unittest.mock import patch

from src import step2_dedup

_SOURCE_TIERS = {
    "tier1_원출처": ["삼성전자 뉴스룸"],
    "tier2_전문지": ["디일렉"],
    "tier3_재인용": ["네이버뉴스 재배포"],
}

_ALIASES = {
    "samsung_electronics": {"aliases": ["삼성전자"], "segment": ["메모리"]},
}


def _article(**overrides):
    article = {
        "id": "a1",
        "title": "삼성전자, HBM4 수율 개선 발표",
        "url": "https://example.com/1",
        "source": "삼성전자 뉴스룸",
        "raw_text": "삼성전자가 HBM4 공정 수율을 개선했다.",
    }
    article.update(overrides)
    return article


def test_group_by_title_similarity_merges_identical_titles():
    articles = [
        _article(id="a1", url="https://a.com/1"),
        _article(id="a2", url="https://b.com/1"),
    ]

    groups = step2_dedup.group_by_title_similarity(articles)

    assert len(groups) == 1
    assert {a["id"] for a in groups[0]} == {"a1", "a2"}


def test_group_by_title_similarity_keeps_distinct_titles_separate():
    articles = [
        _article(id="a1", title="삼성전자, HBM4 수율 개선 발표"),
        _article(id="a2", title="SK하이닉스, 청주 공장 증설 착공"),
    ]

    groups = step2_dedup.group_by_title_similarity(articles)

    assert len(groups) == 2


def test_group_by_title_similarity_merges_titles_differing_only_by_whitespace():
    articles = [
        _article(id="a1", title="삼성전자,   HBM4   수율 개선 발표"),
        _article(id="a2", title="삼성전자, HBM4 수율 개선 발표"),
    ]

    groups = step2_dedup.group_by_title_similarity(articles)

    assert len(groups) == 1


@patch("src.step2_dedup.gemini_client.call_gemini")
def test_cluster_same_event_sends_one_representative_per_title_group(mock_call):
    mock_call.return_value = {"clusters": [["a1"]]}
    articles = [
        _article(id="a1", url="https://a.com/1"),
        _article(id="a2", url="https://b.com/1"),  # 동일 제목, 다른 URL (재배포)
        _article(id="a3", title="SK하이닉스, 청주 공장 증설 착공", url="https://c.com/1"),
    ]

    step2_dedup.cluster_same_event(articles)

    prompt = mock_call.call_args[0][0]
    assert '"a1"' in prompt
    assert '"a3"' in prompt
    assert '"a2"' not in prompt  # a2는 a1과 같은 그룹이라 대표(a1)로만 전달됨


@patch("src.step2_dedup.gemini_client.call_gemini")
def test_cluster_same_event_assigns_same_cluster_id_within_title_group(mock_call):
    mock_call.return_value = {"clusters": [["a1"]]}
    articles = [
        _article(id="a1", url="https://a.com/1"),
        _article(id="a2", url="https://b.com/1"),
    ]

    result = step2_dedup.cluster_same_event(articles)

    by_id = {a["id"]: a for a in result}
    assert by_id["a1"]["cluster_id"] == by_id["a2"]["cluster_id"]


@patch("src.step2_dedup.gemini_client.call_gemini", side_effect=RuntimeError("boom"))
def test_cluster_same_event_keeps_title_group_merged_when_gemini_fails(mock_call):
    articles = [
        _article(id="a1", url="https://a.com/1"),
        _article(id="a2", url="https://b.com/1"),
        _article(id="a3", title="SK하이닉스, 청주 공장 증설 착공", url="https://c.com/1"),
    ]

    result = step2_dedup.cluster_same_event(articles)

    by_id = {a["id"]: a for a in result}
    assert by_id["a1"]["cluster_id"] == by_id["a2"]["cluster_id"]
    assert by_id["a1"]["cluster_id"] != by_id["a3"]["cluster_id"]


def test_cluster_same_event_handles_empty_list():
    assert step2_dedup.cluster_same_event([]) == []


def test_normalize_company_names_matches_alias():
    articles = [_article()]
    result = step2_dedup.normalize_company_names(articles, _ALIASES)
    assert result[0]["companies"] == ["samsung_electronics"]


def test_pick_representative_prefers_tier1_source():
    cluster_articles = [
        _article(id="a1", source="디일렉"),
        _article(id="a2", source="삼성전자 뉴스룸"),
    ]
    representative = step2_dedup.pick_representative(cluster_articles, _SOURCE_TIERS)
    assert representative["id"] == "a2"


def test_tier_rank_orders_tier1_before_tier2_before_tier3_before_unknown():
    assert step2_dedup._tier_rank("삼성전자 뉴스룸", _SOURCE_TIERS) == 0
    assert step2_dedup._tier_rank("디일렉", _SOURCE_TIERS) == 1
    assert step2_dedup._tier_rank("네이버뉴스 재배포", _SOURCE_TIERS) == 2
    assert step2_dedup._tier_rank("알수없는소스", _SOURCE_TIERS) == 3
