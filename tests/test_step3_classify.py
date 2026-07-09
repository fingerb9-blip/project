from unittest.mock import patch

from src import step3_classify

_KEYWORDS = {
    "whitelist": {
        "공급망": ["HBM", "웨이퍼", "파운드리 증설"],
        "규제_무역": ["수출통제", "관세", "반도체법"],
        "반도체_핵심": ["HBM", "파운드리", "D램", "낸드", "웨이퍼", "팹", "노광"],
    },
    "blacklist": {
        "근거없는_시황": ["급등", "테마주", "찌라시"],
    },
}

_CATEGORIES = {
    "메모리": {"segment": ["메모리", "HBM"]},
    "규제·정책": {"segment": []},
}

_CORE_KEYWORDS = _KEYWORDS["whitelist"]["반도체_핵심"]


def _article(**overrides):
    article = {
        "id": "a1",
        "title": "삼성전자, HBM4 수율 개선 발표",
        "url": "https://example.com/1",
        "source": "삼성전자 뉴스룸",
        "raw_text": "삼성전자가 HBM4 공정 수율을 개선했다.",
        "companies": ["samsung_electronics"],
    }
    article.update(overrides)
    return article


def test_compute_relevance_score_high_when_keyword_in_title():
    article = _article(title="삼성전자, HBM4 웨이퍼 수율 개선 발표", raw_text="")
    score = step3_classify.compute_relevance_score(article, _CORE_KEYWORDS)
    assert score >= 3


def test_compute_relevance_score_low_for_single_back_half_mention():
    body = "정부가 가계대출 관리 강화안을 발표하며 은행권 대출 문턱이 높아졌다. " * 10
    body += "업계에서는 반도체 업황 영향으로 파운드리 수요도 변수라는 말이 나온다."
    article = _article(
        id="a2",
        title="정부, 가계대출 관리 강화안 발표...은행권 대출 문턱 높아진다",
        raw_text=body,
        companies=[],
    )
    score = step3_classify.compute_relevance_score(article, _CORE_KEYWORDS)
    assert score <= 1


def test_compute_relevance_score_zero_when_no_core_keyword_mentioned():
    article = _article(
        id="a3",
        title="원/달러 환율, 노조 파업 여파로 급변동",
        raw_text="반도체 업종을 포함한 수출 기업들이 환율 영향을 우려하고 있다.",
        companies=[],
    )
    score = step3_classify.compute_relevance_score(article, _CORE_KEYWORDS)
    assert score == 0


def test_filter_by_keywords_attaches_relevance_score():
    articles = [_article(title="삼성전자, HBM4 웨이퍼 수율 개선 발표", raw_text="")]
    result = step3_classify.filter_by_keywords(articles, _KEYWORDS)
    assert result[0]["relevance_score"] >= 3


def test_filter_by_keywords_excludes_blacklist_regardless_of_relevance_score():
    articles = [
        _article(
            id="a4",
            title="삼성전자 HBM 테마주 급등",
            raw_text="",
        )
    ]
    result = step3_classify.filter_by_keywords(articles, _KEYWORDS)
    assert result == []


def test_filter_by_keywords_keyword_hints_excludes_core_group():
    # 반도체_핵심은 relevance_score 산출 전용이며 keyword_hints에는 노출되지 않는다
    articles = [_article(title="삼성전자, HBM4 웨이퍼 수율 개선 발표", raw_text="")]
    result = step3_classify.filter_by_keywords(articles, _KEYWORDS)
    assert "반도체_핵심" not in result[0]["keyword_hints"]
    assert "공급망" in result[0]["keyword_hints"]


@patch("src.step3_classify.gemini_client.call_gemini")
def test_classify_forces_exclude_when_relevance_low_and_no_keyword_hints(mock_call):
    # 실제 버그 재현: 네이버뉴스 재배포 기사가 본문 후반부에 반도체를 스치듯
    # 언급했을 뿐인데 Gemini가 "확인 필요"로 분류한 경우
    mock_call.return_value = {
        "results": [{"id": "a3", "tier": "확인 필요", "category": []}]
    }
    article = _article(
        id="a3",
        title="원/달러 환율, 노조 파업 여파로 급변동",
        source="네이버뉴스 재배포",
        raw_text="반도체 업종을 포함한 수출 기업들이 환율 영향을 우려하고 있다.",
        companies=[],
    )
    articles = step3_classify.filter_by_keywords([article], _KEYWORDS)

    result = step3_classify.classify_tier_and_category(articles, _CATEGORIES)

    assert result[0]["tier"] == "제외"


@patch("src.step3_classify.gemini_client.call_gemini")
def test_classify_keeps_gemini_tier_when_relevance_high(mock_call):
    mock_call.return_value = {
        "results": [{"id": "a1", "tier": "핵심", "category": ["메모리"]}]
    }
    article = _article(title="삼성전자, HBM4 웨이퍼 수율 개선 발표", raw_text="")
    articles = step3_classify.filter_by_keywords([article], _KEYWORDS)

    result = step3_classify.classify_tier_and_category(articles, _CATEGORIES)

    assert result[0]["tier"] == "핵심"


@patch("src.step3_classify.gemini_client.call_gemini")
def test_classify_does_not_exclude_low_relevance_article_with_regulation_hint(mock_call):
    # 반도체_핵심 키워드는 없지만 규제_무역 화이트리스트에 매칭된 기사는 보호되어야 한다
    mock_call.return_value = {
        "results": [{"id": "a5", "tier": "확인 필요", "category": []}]
    }
    article = _article(
        id="a5",
        title="정부, 반도체법 개정안 발표...수출통제 강화",
        raw_text="",
        companies=[],
    )
    articles = step3_classify.filter_by_keywords([article], _KEYWORDS)

    result = step3_classify.classify_tier_and_category(articles, _CATEGORIES)

    assert result[0]["tier"] == "확인 필요"


@patch("src.step3_classify.gemini_client.call_gemini")
def test_classify_does_not_exclude_low_relevance_article_with_detected_company(mock_call):
    # 기업이 특정된 기사는 핵심 키워드/화이트리스트 힌트가 없어도 강제 제외하지 않는다
    mock_call.return_value = {
        "results": [{"id": "a6", "tier": "핵심", "category": ["파운드리"]}]
    }
    article = _article(
        id="a6",
        title="삼성전자, 공정 설비 신규 구매 계획",
        raw_text="",
        companies=["samsung_electronics"],
    )
    articles = step3_classify.filter_by_keywords([article], _KEYWORDS)

    result = step3_classify.classify_tier_and_category(articles, _CATEGORIES)

    assert result[0]["tier"] == "핵심"
