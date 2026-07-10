import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import rebuild_dashboard  # noqa: E402


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _seed_source_data(base_dir: Path, today: str) -> None:
    _write_json(
        base_dir / "data" / "summarized" / f"{today}.json",
        [
            {
                "id": "seed-a1",
                "title": "삼성전자, 테스트 기사",
                "url": "https://example.com/news/1",
                "source": "디일렉",
                "summary": "테스트 요약입니다.",
                "confirmation_tag": "[확정]",
                "summary_fallback": False,
                "category": ["메모리"],
            }
        ],
    )
    _write_json(base_dir / "data" / "classified" / f"{today}.json", [])
    _write_json(
        base_dir / "data" / "raw" / f"{today}.json",
        [{"title": "삼성전자, 테스트 기사", "source": "디일렉"}],
    )


def test_rebuild_all_writes_new_template_for_each_seeded_date(tmp_path):
    _seed_source_data(tmp_path, "2026-07-08")
    _seed_source_data(tmp_path, "2026-07-09")

    rebuilt = rebuild_dashboard.rebuild_all(tmp_path)

    assert set(rebuilt) == {"2026-07-08", "2026-07-09"}
    html_08 = (tmp_path / "data" / "dashboard" / "2026-07-08.html").read_text(encoding="utf-8")
    html_09 = (tmp_path / "data" / "dashboard" / "2026-07-09.html").read_text(encoding="utf-8")
    # 7/8과 7/9가 같은 새 구조 요소(필터 바)를 공유해야 "디자인이 통일됐다"고 볼 수 있다.
    assert 'class="filter"' in html_08
    assert 'class="filter"' in html_09
    assert "삼성전자, 테스트 기사" in html_08


def test_rebuild_all_returns_empty_list_when_no_source_data(tmp_path):
    assert rebuild_dashboard.rebuild_all(tmp_path) == []


def test_rebuild_all_falls_back_to_classified_when_summarized_missing(tmp_path):
    """summarized.json 없이 classified.json만 있는 날짜(예: gitignore로 못 받아온 원격 실행분)."""
    _write_json(
        tmp_path / "data" / "classified" / "2026-07-09.json",
        [
            {
                "id": "seed-a2",
                "title": "SK하이닉스, 헤드라인만 남은 기사",
                "url": "https://example.com/news/2",
                "source": "디일렉",
                "tier": "핵심",
                "category": ["메모리"],
            },
            {
                "id": "seed-a3",
                "title": "제외된 기사",
                "url": "https://example.com/news/3",
                "source": "디일렉",
                "tier": "제외",
                "category": [],
            },
        ],
    )

    rebuilt = rebuild_dashboard.rebuild_all(tmp_path)

    assert rebuilt == ["2026-07-09"]
    html_out = (tmp_path / "data" / "dashboard" / "2026-07-09.html").read_text(encoding="utf-8")
    assert "SK하이닉스, 헤드라인만 남은 기사" in html_out
    assert "제외된 기사" not in html_out  # tier="제외"는 복원 대상 아님
    assert "요약 없음" in html_out  # 요약문 복원 불가 -> fallback 카드로 표시
    assert 'class="filter"' in html_out  # 새 구조 요소는 정상 적용


def test_rebuild_style_and_index_works_without_source_data(tmp_path):
    dashboard_dir = tmp_path / "data" / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")

    rebuild_dashboard.rebuild_style_and_index(tmp_path)

    style_css = (dashboard_dir / "style.css").read_text(encoding="utf-8")
    assert "--paper" in style_css  # 새 디자인 토큰이 반영됐는지 확인
    assert (dashboard_dir / "index.html").exists()


def test_rebuild_style_and_index_renders_report_card_for_existing_page(tmp_path):
    """v2 인덱스는 헤드라인 미리보기가 아니라 날짜별 리포트 카드로 목록을 보여준다 (§5-1)."""
    _seed_source_data(tmp_path, "2026-07-08")
    dashboard_dir = tmp_path / "data" / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")

    rebuild_dashboard.rebuild_style_and_index(tmp_path)

    index_html = (dashboard_dir / "index.html").read_text(encoding="utf-8")
    assert 'href="2026-07-08.html"' in index_html
    assert "리포트 읽기" in index_html


def test_preview_diffs_shows_diff_against_stale_existing_file(tmp_path):
    _seed_source_data(tmp_path, "2026-07-09")
    dashboard_dir = tmp_path / "data" / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "2026-07-09.html").write_text("<html>old</html>", encoding="utf-8")

    output = rebuild_dashboard.preview_diffs(tmp_path, sample_size=1)

    assert "2026-07-09" in output
    assert "-<html>old</html>" in output
    assert "+<!doctype html>" in output


def test_preview_diffs_does_not_write_any_files(tmp_path):
    _seed_source_data(tmp_path, "2026-07-09")
    dashboard_dir = tmp_path / "data" / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "2026-07-09.html").write_text("<html>old</html>", encoding="utf-8")

    rebuild_dashboard.preview_diffs(tmp_path, sample_size=1)

    assert (dashboard_dir / "2026-07-09.html").read_text(encoding="utf-8") == "<html>old</html>"


def test_preview_diffs_reports_no_changes_when_content_already_matches(tmp_path):
    _seed_source_data(tmp_path, "2026-07-09")
    rebuild_dashboard.rebuild_all(tmp_path)  # 현재 템플릿으로 이미 최신 상태로 만들어 둠

    output = rebuild_dashboard.preview_diffs(tmp_path, sample_size=1)

    assert "변경 없음" in output


def test_preview_diffs_limits_to_sample_size_most_recent_dates(tmp_path):
    _seed_source_data(tmp_path, "2026-07-08")
    _seed_source_data(tmp_path, "2026-07-09")
    dashboard_dir = tmp_path / "data" / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "2026-07-08.html").write_text("<html>old</html>", encoding="utf-8")
    (dashboard_dir / "2026-07-09.html").write_text("<html>old</html>", encoding="utf-8")

    output = rebuild_dashboard.preview_diffs(tmp_path, sample_size=1)

    assert "=== 2026-07-09 ===" in output
    assert "=== 2026-07-08 ===" not in output


def test_preview_diffs_warns_when_no_source_data(tmp_path):
    output = rebuild_dashboard.preview_diffs(tmp_path, sample_size=3)
    assert "[WARN]" in output
