"""Step 0~6 순차 실행 진입점."""

from datetime import date

from src import (
    step0_init,
    step1_collect,
    step2_dedup,
    step3_classify,
    step4_summarize,
    step5_assemble,
    step6_send,
)


def main() -> None:
    """오늘 날짜 기준으로 Step 0부터 Step 6까지 순차 실행한다."""
    today = date.today().isoformat()

    # TODO: config = step0_init.run(today)
    # TODO: raw_articles = step1_collect.run(config["feeds"], config["paths"]["raw"])
    # TODO: dedup_articles = step2_dedup.run(raw_articles, config["aliases"], config["source_tiers"], config["paths"]["dedup"])
    # TODO: classified_articles = step3_classify.run(dedup_articles, config["categories"], config["keywords"], config["paths"]["classified"])
    # TODO: summarized_articles = step4_summarize.run(classified_articles, config["source_tiers"], config["paths"]["summarized"])
    # TODO: briefing = step5_assemble.run(summarized_articles, collection_stats, config["paths"]["archive"])
    # TODO: step6_send.run(config["paths"]["archive"], config["smtp"])
    raise NotImplementedError


if __name__ == "__main__":
    main()
