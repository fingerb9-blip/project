"""과거 대시보드 페이지를 최신 디자인(step5_assemble)으로 재생성한다.

대시보드_디자인_개편_명세.md §7 참고 — 날짜별 HTML(`data/dashboard/YYYY-MM-DD.html`)은
그날 한 번 저장되면 이후 실행에서 다시 만들어지지 않는 정적 파일이다. `_DASHBOARD_CSS`만
바꿔서는 칩·필터 바·날짜 내비 같은 새 구조 요소가 이미 저장된 과거 페이지에 붙지 않으므로,
이 스크립트가 `data/summarized/`, `data/classified/` 원본 데이터로 각 날짜 페이지를
새 템플릿으로 다시 렌더링한다(backfill).

Usage:
    python scripts/rebuild_dashboard.py              # 전체 재생성 (원본 JSON 필요)
    python scripts/rebuild_dashboard.py --style-only  # style.css/index.html만 갱신
                                                       # (원본 데이터 없어도 동작 — CSS 변경은
                                                       # 공유 스타일시트라 즉시 전 페이지에 반영됨)
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from main import _compute_collection_stats  # noqa: E402
from src import step5_assemble  # noqa: E402


def _load_json(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_feeds(base_dir: Path) -> list[dict]:
    feeds_path = base_dir / "sources" / "feeds.yaml"
    if not feeds_path.exists():
        return []
    with feeds_path.open(encoding="utf-8") as f:
        feeds_config = yaml.safe_load(f) or {}
    return feeds_config.get("feeds") or []


def _reconstruct_from_classified(classified: list[dict]) -> list[dict]:
    """summarized.json이 없을 때 classified.json의 '핵심' tier 기사로 느슨하게 복원한다.

    요약문·[확정]/[관측] 태그는 Step 4(Gemini 요약)의 산출물이라 classified.json에는
    없다 — 복원 불가능하므로 summary_fallback=True(헤드라인+링크만)로 표시한다.
    정확도가 제한적인 폴백이다 (§7).
    """
    return [
        {
            "title": article["title"],
            "url": article["url"],
            "source": article["source"],
            "summary": None,
            "confirmation_tag": None,
            "summary_fallback": True,
            "category": article.get("category") or [],
        }
        for article in classified
        if article.get("tier") == "핵심"
    ]


def _load_or_reconstruct_summarized(base_dir: Path, today: str) -> tuple[list[dict], Path | None]:
    """summarized.json이 있으면 그대로, 없으면 classified.json에서 느슨하게 복원한다.

    Returns:
        (기사 리스트, 시각 기준으로 쓸 파일 경로 — updated_at 계산용. 둘 다 없으면 (=[], None))
    """
    summarized_path = base_dir / "data" / "summarized" / f"{today}.json"
    summarized = _load_json(summarized_path)
    if summarized is not None:
        return summarized, summarized_path

    classified_path = base_dir / "data" / "classified" / f"{today}.json"
    classified = _load_json(classified_path)
    if classified is not None:
        return _reconstruct_from_classified(classified), classified_path

    return [], None


def _dates_with_source_data(base_dir: Path) -> list[str]:
    """summarized.json 또는 classified.json(폴백 복원용)이 있는 날짜를 모두 모은다."""
    dates = set()
    for sub in ("summarized", "classified"):
        d = base_dir / "data" / sub
        if d.exists():
            dates.update(p.stem for p in d.glob("*.json"))
    return sorted(dates)


def rebuild_all(base_dir: Path) -> list[str]:
    """data/summarized/*.json(있으면) 또는 data/classified/*.json(폴백)으로
    모든 날짜를 새 템플릿으로 재생성한다.

    과거 날짜의 "진행 중 이슈" 섹션은 채우지 않는다 — issues.json은 그날의 스냅숏이
    아니라 "현재" 이슈 상태만 가지고 있어, 과거 페이지에 지금의 이슈 목록을 붙이면
    시점이 맞지 않는 정보를 보여주게 된다.

    Returns:
        재생성에 성공한 날짜 목록 (최신순)
    """
    dates = _dates_with_source_data(base_dir)
    if not dates:
        return []

    dashboard_dir = base_dir / "data" / "dashboard"
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    feeds = _load_feeds(base_dir)
    all_dates = sorted(dates, reverse=True)

    rebuilt = []
    for today in dates:
        summarized, timestamp_source = _load_or_reconstruct_summarized(base_dir, today)
        classified = _load_json(base_dir / "data" / "classified" / f"{today}.json") or []
        raw_articles = _load_json(base_dir / "data" / "raw" / f"{today}.json") or []
        pending_review = [a for a in classified if a.get("tier") == "확인 필요"]
        collection_stats = _compute_collection_stats(base_dir, {"feeds": feeds}, raw_articles, today)

        updated_at = (
            datetime.fromtimestamp(timestamp_source.stat().st_mtime, tz=timezone.utc).isoformat()
            if timestamp_source
            else None
        )

        html_out = step5_assemble.build_dashboard_html(
            summarized,
            pending_review,
            collection_stats,
            today,
            all_dates=all_dates,
            active_issues=None,
            updated_at=updated_at,
        )
        (dashboard_dir / f"{today}.html").write_text(html_out, encoding="utf-8")
        rebuilt.append(today)

    return rebuilt


def rebuild_style_and_index(base_dir: Path) -> None:
    """style.css와 index.html만 최신 디자인으로 다시 쓴다 (원본 JSON 없어도 동작).

    style.css는 모든 페이지가 공유하므로, 이것만 다시 써도 색·타이포·카드 룩은
    과거 페이지까지 즉시 통일된다. 단 칩/필터 바/날짜 내비 같은 새 구조 요소는
    rebuild_all()로 페이지 자체를 재생성해야만 과거 페이지에 붙는다.
    """
    dashboard_dir = base_dir / "data" / "dashboard"
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    state_path = base_dir / "data" / "state" / "run_status.json"
    issues_path = base_dir / "data" / "state" / "issues.json"

    (dashboard_dir / "style.css").write_text(step5_assemble._DASHBOARD_CSS, encoding="utf-8")

    dates = sorted(
        (p.stem for p in dashboard_dir.glob("*.html") if p.stem != "index"), reverse=True
    )
    latest_core_count = None
    latest_headlines = None
    if dates:
        latest_summarized, _ = _load_or_reconstruct_summarized(base_dir, dates[0])
        if latest_summarized:
            latest_core_count = len(latest_summarized)
            latest_headlines = [a["title"] for a in latest_summarized[:3]]

    index_html = step5_assemble.build_index_html(
        dashboard_dir,
        state_path,
        issues_path=issues_path if issues_path.exists() else None,
        latest_core_count=latest_core_count,
        latest_headlines=latest_headlines,
    )
    (dashboard_dir / "index.html").write_text(index_html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--style-only",
        action="store_true",
        help="원본 JSON 없이 style.css/index.html만 최신 디자인으로 갱신",
    )
    args = parser.parse_args()

    if args.style_only:
        rebuild_style_and_index(BASE_DIR)
        print("[OK] style.css / index.html 갱신 완료 (--style-only)")
        return

    rebuilt = rebuild_all(BASE_DIR)
    if not rebuilt:
        print(
            "[WARN] data/summarized/*.json이 없어 날짜별 페이지를 재생성할 수 없습니다. "
            "--style-only와 동일하게 style.css/index.html만 갱신합니다."
        )
        rebuild_style_and_index(BASE_DIR)
        return

    rebuild_style_and_index(BASE_DIR)
    print(f"[OK] {len(rebuilt)}개 날짜 페이지 재생성 완료: {', '.join(rebuilt)}")


if __name__ == "__main__":
    main()
