"""Step 7. 이메일 뉴스레터 — 명단 구독자에게 그날 브리핑을 발송한다 (무료, 지인 대상)."""

import logging
import os

logger = logging.getLogger(__name__)


def load_subscribers(raw: str | None = None) -> list[str]:
    """구독자 명단을 로드한다.

    Args:
        raw: 콤마 구분 이메일 문자열. None이면 환경변수 SUBSCRIBERS에서 읽는다.

    Returns:
        정제된 이메일 리스트 (공백 제거·'@' 포함·중복 제거, 입력 순서 유지). 없으면 [].
    """
    if raw is None:
        raw = os.environ.get("SUBSCRIBERS", "")
    seen: dict[str, None] = {}
    for part in raw.split(","):
        email = part.strip()
        if "@" in email and email not in seen:
            seen[email] = None
    return list(seen)
