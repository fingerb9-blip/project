"""인간 피드백 인테이크 — GitHub 이슈(노이즈 신고)를 feedback_queue.json에 기록한다."""

import argparse
import json
import re
from pathlib import Path

_FIELD_PATTERN = re.compile(r"^(article_id|url|title|reason):\s*(.+)$", re.MULTILINE)


def parse_issue_body(body: str) -> dict:
    """이슈 본문에서 article_id/url/title/reason 필드를 파싱한다.

    대시보드의 "노이즈로 표시" 버튼이 만든 이슈 본문은 다음 형식의 필드를 담고 있다:
        article_id: <sha1>
        url: <원문 URL>
        title: <기사 제목>
        reason: noise

    Args:
        body: GitHub 이슈 본문 텍스트

    Returns:
        {article_id, url, title, reason} dict (누락 필드는 빈 문자열, reason 기본값은 "noise")
    """
    fields = {key: value.strip() for key, value in _FIELD_PATTERN.findall(body or "")}
    return {
        "article_id": fields.get("article_id", ""),
        "url": fields.get("url", ""),
        "title": fields.get("title", ""),
        "reason": fields.get("reason", "noise"),
    }


def append_to_queue(queue_path: Path, entry: dict) -> list[dict]:
    """feedback_queue.json에 새 신고 항목을 추가한다.

    Args:
        queue_path: data/state/feedback_queue.json 경로
        entry: {article_id, flagged_at, reason, title, url} dict

    Returns:
        갱신된 전체 큐 리스트
    """
    queue_path = Path(queue_path)
    queue = []
    if queue_path.exists():
        with queue_path.open(encoding="utf-8") as f:
            queue = json.load(f)

    queue.append(entry)

    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

    return queue


def _cli_main(argv: list[str] | None = None) -> None:
    """GitHub Actions noise_feedback.yml에서 이슈 오픈 이벤트로 호출되는 CLI 진입점."""
    parser = argparse.ArgumentParser(description="노이즈 신고 이슈를 feedback_queue.json에 기록")
    parser.add_argument("--body", required=True)
    parser.add_argument("--flagged-at", required=True)
    parser.add_argument("--queue-path", required=True)
    args = parser.parse_args(argv)

    parsed = parse_issue_body(args.body)
    if not parsed["article_id"]:
        raise SystemExit("이슈 본문에서 article_id를 찾을 수 없습니다")

    entry = {
        "article_id": parsed["article_id"],
        "flagged_at": args.flagged_at,
        "reason": parsed["reason"],
        "title": parsed["title"],
        "url": parsed["url"],
    }
    append_to_queue(Path(args.queue_path), entry)


if __name__ == "__main__":
    _cli_main()
