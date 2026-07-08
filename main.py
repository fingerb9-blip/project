"""Step 0~6 순차 실행 진입점."""

import json
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from src import (
    step0_init,
    step1_collect,
    step2_dedup,
    step3_classify,
    step4_summarize,
    step5_assemble,
    step6_send,
)


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

    config = step0_init.run(today)
    paths = config["paths"]

    raw_articles = step1_collect.run(config["feeds"], paths["raw"])
    dedup_articles = step2_dedup.run(
        raw_articles, config["company_aliases"], config["source_tiers"], paths["dedup"]
    )
    classified_articles = step3_classify.run(
        dedup_articles, config["categories"], config["keywords"], paths["classified"]
    )
    summarized_articles = step4_summarize.run(
        classified_articles, config["source_tiers"], paths["summarized"]
    )

    pending_review = [a for a in classified_articles if a.get("tier") == "확인 필요"]
    collection_stats = _compute_collection_stats(base_dir, config["feeds"], raw_articles, today)
    step5_assemble.run(summarized_articles, pending_review, collection_stats, paths["archive"])

    smtp_config = {
        "host": os.environ["SMTP_HOST"],
        "port": os.environ["SMTP_PORT"],
        "user": os.environ["SMTP_USER"],
        "password": os.environ["SMTP_PASSWORD"],
        "to": os.environ["SMTP_TO"],
    }
    step6_send.run(paths["archive"], smtp_config)


if __name__ == "__main__":
    main()
