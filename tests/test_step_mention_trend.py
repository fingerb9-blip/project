import json

from src import step_mention_trend

_ALIASES = {
    "samsung_electronics": {"aliases": ["삼성전자"], "segment": ["메모리"]},
    "sk_hynix": {"aliases": ["SK하이닉스"], "segment": ["메모리"]},
}

_TECH_KEYWORDS = [
    {"canonical": "HBM", "aliases": ["HBM3", "HBM4"]},
    {"canonical": "EUV", "aliases": ["극자외선"]},
]


def test_load_tech_keywords_reads_yaml(tmp_path):
    path = tmp_path / "tech_keywords.yaml"
    path.write_text('keywords:\n  - canonical: "HBM"\n    aliases: ["HBM4"]\n', encoding="utf-8")

    keywords = step_mention_trend.load_tech_keywords(path)

    assert keywords == [{"canonical": "HBM", "aliases": ["HBM4"]}]


def test_count_company_mentions_uses_display_name():
    articles = [
        {"companies": ["samsung_electronics"]},
        {"companies": ["samsung_electronics", "sk_hynix"]},
    ]

    counts = step_mention_trend.count_company_mentions(articles, _ALIASES)

    assert counts == {"삼성전자": 2, "SK하이닉스": 1}


def test_match_tech_keywords_matches_alias_not_just_canonical():
    matched = step_mention_trend.match_tech_keywords("삼성전자, HBM4 공급 확대", _TECH_KEYWORDS)

    assert matched == ["HBM"]


def test_count_keyword_mentions_counts_title_and_raw_text():
    articles = [
        {"title": "HBM4 수율 개선", "raw_text": ""},
        {"title": "EUV 노광 장비 도입", "raw_text": "극자외선 공정 확대"},
    ]

    counts = step_mention_trend.count_keyword_mentions(articles, _TECH_KEYWORDS)

    assert counts == {"HBM": 1, "EUV": 1}


def test_run_flags_spike_when_count_far_above_moving_average(tmp_path):
    trends_dir = tmp_path / "trends"
    trends_dir.mkdir()
    for days_ago in range(1, 8):
        day = f"2026-07-{9 - days_ago:02d}"
        (trends_dir / f"{day}.json").write_text(
            json.dumps({"date": day, "companies": [{"name": "삼성전자", "count": 1, "is_spike": False}], "keywords": []}),
            encoding="utf-8",
        )
    articles = [{"companies": ["samsung_electronics"], "title": "", "raw_text": ""} for _ in range(5)]

    result = step_mention_trend.run(articles, _ALIASES, _TECH_KEYWORDS, str(trends_dir), "2026-07-09")

    assert result["companies"] == [{"name": "삼성전자", "count": 5, "is_spike": True}]
    saved = json.loads((trends_dir / "2026-07-09.json").read_text(encoding="utf-8"))
    assert saved == result


def test_run_does_not_flag_spike_on_cold_start_with_low_count(tmp_path):
    trends_dir = tmp_path / "trends"
    articles = [{"companies": ["samsung_electronics"], "title": "", "raw_text": ""}]

    result = step_mention_trend.run(articles, _ALIASES, _TECH_KEYWORDS, str(trends_dir), "2026-07-09")

    assert result["companies"] == [{"name": "삼성전자", "count": 1, "is_spike": False}]
