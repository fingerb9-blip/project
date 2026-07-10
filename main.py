"""Step 0~6 순차 실행 진입점."""

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from src import (
    notify,
    radar_weekly,
    run_status,
    step0_init,
    step1_collect,
    step2_dedup,
    step3_classify,
    step4_5_issue_match,
    step4_summarize,
    step5_assemble,
    step6_send,
    stock_fetch,
)

KST = timezone(timedelta(hours=9))


def _compute_collection_stats(
    base_dir: Path, feeds_config: dict, today_articles: list[dict], today: str
) -> dict:
    """소스별 오늘 수집 건수와 최근 7일 평균을 계산한다 (Step 5 수집 상태 섹션용)."""
    raw_dir = base_dir / "data" / "raw"
    sources = [feed["name"] for feed in feeds_config.get("feeds") or []]
    stats = {}

    for source in sources:
        today_count = sum(1 for a in today_articles if a["source"] == source)

        past_counts = []
        for days_ago in range(1, 8):
            day = (date.fromisoformat(today) - timedelta(days=days_ago)).isoformat()
            path = raw_dir / f"{day}.json"
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as f:
                past_articles = json.load(f)
            past_counts.append(sum(1 for a in past_articles if a["source"] == source))

        avg7d = sum(past_counts) / len(past_counts) if past_counts else 0.0
        stats[source] = {"today": today_count, "avg7d": avg7d}

    return stats


def _maybe_run_weekly_radar(base_dir: Path, config: dict, today: str, weekday: int) -> None:
    """매주 월요일(KST)에만 경쟁 구도 레이더를 갱신한다. 실패해도 파이프라인은 계속 진행한다.

    Args:
        weekday: KST 기준 요일(datetime.weekday(), 월요일=0). today는 파이프라인 전체에서
            공유하는 UTC 라벨 날짜이므로 여기서 요일을 다시 계산하면 안 된다 — 호출부가
            KST 기준으로 계산한 값을 그대로 넘겨야 한다.
    """
    if not radar_weekly.is_radar_day(weekday):
        return
    try:
        tracked_companies = radar_weekly.load_tracked_companies(
            base_dir / "config" / "radar_companies.yaml"
        )
        radar_weekly.run(
            dedup_dir=str(base_dir / "data" / "dedup"),
            issues_path=str(base_dir / "data" / "state" / "issues.json"),
            aliases_config=config["company_aliases"],
            tracked_companies=tracked_companies,
            today=today,
            output_dir=str(base_dir / "data" / "radar"),
        )
    except Exception as exc:
        notify.notify_warning("경쟁 구도 레이더 갱신 실패", f"{type(exc).__name__}: {exc}")


def _update_stock_prices(stock_prices_path: Path) -> None:
    """오늘의 시장 현황 패널의 주가 카드용 데이터를 갱신한다.

    보조 데이터라 실패해도 파이프라인을 막지 않는다 — stock_fetch.run() 자체도
    종목별로 실패를 흡수하지만, 파일 시스템 오류 등 예상 밖 실패까지 여기서 막아준다.
    """
    try:
        stock_fetch.run(str(stock_prices_path))
    except Exception as exc:
        notify.notify_warning("주가 데이터 갱신 실패", f"{type(exc).__name__}: {exc}")


def main() -> None:
    """오늘 날짜 기준으로 Step 0부터 Step 6까지 순차 실행한다."""
    load_dotenv()
    base_dir = Path(__file__).resolve().parent
    today = date.today().isoformat()
    pending_path = base_dir / "config" / "keywords_pending.yaml"

    try:
        config = step0_init.run(today)
    except step0_init.DuplicateRunError as exc:
        print(f"[SKIP] {exc}")
        return
    paths = config["paths"]

    steps_completed = []
    raw_articles = []
    try:
        raw_articles = step1_collect.run(config["feeds"], paths["raw"])
        steps_completed.append("collect")

        dedup_articles = step2_dedup.run(
            raw_articles, config["company_aliases"], config["source_tiers"], paths["dedup"]
        )
        steps_completed.append("dedup")

        classified_articles = step3_classify.run(
            dedup_articles, config["categories"], config["keywords"], paths["classified"]
        )
        steps_completed.append("classify")

        summarized_articles = step4_summarize.run(
            classified_articles, config["source_tiers"], paths["summarized"]
        )
        steps_completed.append("summarize")

        core_articles = [a for a in summarized_articles if not a.get("summary_fallback")]
        step4_5_issue_match.run(core_articles, config["company_aliases"], paths["issues"], today)
        steps_completed.append("issue_match")

        _maybe_run_weekly_radar(base_dir, config, today, datetime.now(KST).weekday())

        pending_review = [a for a in classified_articles if a.get("tier") == "확인 필요"]
        collection_stats = _compute_collection_stats(base_dir, config["feeds"], raw_articles, today)
        github_repo = os.environ.get("GITHUB_REPOSITORY")
        repo_url = f"https://github.com/{github_repo}" if github_repo else None
        _update_stock_prices(paths["stock_prices"])
        step5_assemble.run(
            summarized_articles,
            pending_review,
            collection_stats,
            paths["archive"],
            paths["dashboard_dir"],
            today,
            paths["state"],
            paths["issues"],
            radar_data=step5_assemble.load_latest_radar(base_dir / "data" / "radar"),
            repo_url=repo_url,
            stock_prices_path=paths["stock_prices"],
        )
        steps_completed.append("assemble")

        if not step6_send.run(paths["dashboard_dir"], today):
            raise RuntimeError("Step 6 검증 실패 (08:30까지 대시보드 미갱신)")
        steps_completed.append("send")
    except Exception as exc:
        prev_status = run_status.load_status(paths["state"])
        run_status.save_status(
            paths["state"],
            {
                "last_run_date": today,
                "last_run_status": "failed",
                "last_success_at": prev_status.get("last_success_at") if prev_status else None,
                "steps_completed": steps_completed,
                "article_count": len(raw_articles),
                "failed_sources": [],
            },
        )
        index_html = step5_assemble.build_index_html(
            paths["dashboard_dir"],
            paths["state"],
            issues_path=paths["issues"],
            radar_data=step5_assemble.load_latest_radar(base_dir / "data" / "radar"),
            pending_keywords=step5_assemble.load_pending_keywords(pending_path),
        )
        (paths["dashboard_dir"] / "index.html").write_text(index_html, encoding="utf-8")
        if notify.looks_like_auth_error(exc):
            notify.notify_auth_error("파이프라인 실행 중 인증 오류", f"{type(exc).__name__}: {exc}")
        else:
            notify.notify_failure("파이프라인 실행 실패", f"{type(exc).__name__}: {exc}")
        raise

    run_status.save_status(
        paths["state"],
        {
            "last_run_date": today,
            "last_run_status": "success",
            "last_success_at": datetime.now(KST).isoformat(),
            "steps_completed": steps_completed,
            "article_count": len(raw_articles),
            "failed_sources": [],
        },
    )
    index_html = step5_assemble.build_index_html(
        paths["dashboard_dir"],
        paths["state"],
        issues_path=paths["issues"],
        radar_data=step5_assemble.load_latest_radar(base_dir / "data" / "radar"),
        pending_keywords=step5_assemble.load_pending_keywords(pending_path),
    )
    (paths["dashboard_dir"] / "index.html").write_text(index_html, encoding="utf-8")


if __name__ == "__main__":
    main()
