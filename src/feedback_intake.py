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
