"""Step 0~6 순차 실행 진입점."""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from src import (
    notify,
    run_status,
    step0_init,
    step1_collect,
    step2_dedup,
    step3_classify,
    step4_summarize,
    step5_assemble,
    step6_send,
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


def main() -> None:
    """오늘 날짜 기준으로 Step 0부터 Step 6까지 순차 실행한다."""
    load_dotenv()
    base_dir = Path(__file__).resolve().parent
    today = date.today().isoformat()

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

        pending_review = [a for a in classified_articles if a.get("tier") == "확인 필요"]
        collection_stats = _compute_collection_stats(base_dir, config["feeds"], raw_articles, today)
        step5_assemble.run(
            summarized_articles,
            pending_review,
            collection_stats,
            paths["archive"],
            paths["dashboard_dir"],
            today,
            paths["state"],
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


if __name__ == "__main__":
    main()
