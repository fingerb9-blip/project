"""Step 7. 이메일 뉴스레터 — 명단 구독자에게 그날 브리핑을 발송한다 (무료, 지인 대상)."""

import logging
import os
from pathlib import Path

from src import step5_assemble

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


_STYLE_LINK = '<link rel="stylesheet" href="style.css">'


def build_standalone_html(dashboard_dir: Path, today: str) -> str:
    """그날 대시보드 HTML의 외부 CSS 링크를 인라인 <style>로 치환한 자립형 HTML을 만든다.

    이메일 첨부는 style.css를 함께 못 보내므로, 브라우저에서 단독으로 열어도 스타일이
    유지되도록 CSS를 문서 안에 넣는다.
    """
    html_text = (Path(dashboard_dir) / f"{today}.html").read_text(encoding="utf-8")
    inline_style = f"<style>{step5_assemble._DASHBOARD_CSS}</style>"
    return html_text.replace(_STYLE_LINK, inline_style)
