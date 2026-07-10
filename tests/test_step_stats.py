import json

from src import step_stats


def _classified(**overrides):
    article = {
        "id": "a1",
        "title": "삼성전자 HBM4 공개",
        "url": "https://example.com/1",
        "source": "디일렉",
        "raw_text": "삼성전자가 HBM4를 공개했다",
        "tier": "핵심",
        "category": ["메모리"],
    }
    article.update(overrides)
    return article


def _summarized(**overrides):
    article = {
        "id": "a1",
        "title": "삼성전자 HBM4 공개",
        "source": "디일렉",
        "summary": "삼성전자가 HBM4를 공개했다.",
        "confirmation_tag": "[확정]",
        "summary_fallback": False,
        "category": ["메모리"],
    }
    article.update(overrides)
    return article


def test_compute_daily_stats_counts_total_and_category():
    classified = [
        _classified(id="a1", category=["메모리"]),
        _classified(id="a2", category=["메모리"]),
        _classified(id="a3", category=["파운드리"], tier="확인 필요"),
    ]
    stats = step_stats.compute_daily_stats(classified, [], "2026-07-10")

    assert stats["date"] == "2026-07-10"
    assert stats["total_articles"] == 3
    assert stats["by_category"] == {"메모리": 2, "파운드리": 1}


def test_compute_daily_stats_excludes_excluded_tier():
    classified = [
        _classified(id="a1", tier="핵심"),
        _classified(id="a2", tier="제외"),
    ]
    stats = step_stats.compute_daily_stats(classified, [], "2026-07-10")

    assert stats["total_articles"] == 1


def test_compute_daily_stats_counts_by_source():
    classified = [
        _classified(id="a1", source="디일렉"),
        _classified(id="a2", source="디일렉"),
        _classified(id="a3", source="EE Times"),
    ]
    stats = step_stats.compute_daily_stats(classified, [], "2026-07-10")

    assert stats["by_source"] == {"디일렉": 2, "EE Times": 1}


def test_compute_daily_stats_counts_by_confidence_from_summarized_only():
    classified = [_classified(id="a1"), _classified(id="a2", tier="확인 필요")]
    summarized = [
        _summarized(id="a1", confirmation_tag="[확정]"),
        _summarized(id="a2", confirmation_tag="[관측]"),
        _summarized(id="a3", summary_fallback=True, confirmation_tag=None),
    ]
    stats = step_stats.compute_daily_stats(classified, summarized, "2026-07-10")

    assert stats["by_confidence"] == {"확정": 1, "관측": 1, "요약없음": 1}


def test_compute_daily_stats_top_keywords_uses_dictionary_matching():
    classified = [
        _classified(id="a1", title="삼성전자 HBM4 공개", raw_text="삼성전자가 HBM4를 공개했다"),
        _classified(id="a2", title="삼성전자 파운드리 증설", raw_text="삼성전자 파운드리 증설 발표"),
        _classified(id="a3", title="SK하이닉스 HBM 공급", raw_text="SK하이닉스가 HBM을 공급한다"),
    ]
    stats = step_stats.compute_daily_stats(classified, [], "2026-07-10")

    keywords = {k["keyword"]: k["count"] for k in stats["top_keywords"]}
    assert keywords["삼성전자"] == 2
    assert keywords["HBM"] == 2
    assert keywords["SK하이닉스"] == 1


def test_compute_daily_stats_top_keywords_limited_to_ten():
    stats = step_stats.compute_daily_stats([], [], "2026-07-10")
    assert stats["top_keywords"] == []


def test_compute_daily_stats_noise_reported_always_zero():
    stats = step_stats.compute_daily_stats([], [], "2026-07-10")
    assert stats["noise_reported"] == 0


def test_save_daily_stats_writes_json_file(tmp_path):
    stats = {"date": "2026-07-10", "total_articles": 0, "by_category": {}, "by_source": {},
             "by_confidence": {}, "top_keywords": [], "noise_reported": 0}
    path = step_stats.save_daily_stats(tmp_path, stats)

    assert path == tmp_path / "2026-07-10.json"
    assert json.loads(path.read_text(encoding="utf-8")) == stats


def test_build_stats_all_merges_all_daily_files_sorted_ascending(tmp_path):
    for date, total in [("2026-07-09", 5), ("2026-07-08", 3), ("2026-07-10", 7)]:
        (tmp_path / f"{date}.json").write_text(
            json.dumps({"date": date, "total_articles": total}), encoding="utf-8"
        )

    entries = step_stats.build_stats_all(tmp_path)

    assert [e["date"] for e in entries] == ["2026-07-08", "2026-07-09", "2026-07-10"]
    saved = json.loads((tmp_path / "stats_all.json").read_text(encoding="utf-8"))
    assert saved == entries


def test_build_stats_all_ignores_its_own_output_file(tmp_path):
    (tmp_path / "2026-07-08.json").write_text(json.dumps({"date": "2026-07-08"}), encoding="utf-8")
    (tmp_path / "stats_all.json").write_text(json.dumps([{"date": "stale"}]), encoding="utf-8")

    entries = step_stats.build_stats_all(tmp_path)

    assert [e["date"] for e in entries] == ["2026-07-08"]


def test_build_stats_all_recomputes_fully_not_append(tmp_path):
    (tmp_path / "2026-07-08.json").write_text(json.dumps({"date": "2026-07-08"}), encoding="utf-8")
    step_stats.build_stats_all(tmp_path)

    (tmp_path / "2026-07-08.json").write_text(
        json.dumps({"date": "2026-07-08", "total_articles": 99}), encoding="utf-8"
    )
    entries = step_stats.build_stats_all(tmp_path)

    assert entries == [{"date": "2026-07-08", "total_articles": 99}]


def test_run_writes_daily_and_merged_stats(tmp_path):
    classified = [_classified(id="a1", category=["메모리"])]
    summarized = [_summarized(id="a1")]

    entries = step_stats.run(classified, summarized, "2026-07-10", str(tmp_path))

    assert (tmp_path / "2026-07-10.json").exists()
    assert (tmp_path / "stats_all.json").exists()
    assert entries[0]["date"] == "2026-07-10"
    assert entries[0]["total_articles"] == 1
