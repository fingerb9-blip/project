"""Step 7. 이메일 뉴스레터 — 명단 구독자에게 그날 브리핑을 발송한다 (무료, 지인 대상)."""

import html
import json
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


def _load_core_articles(summarized_path: Path) -> list[dict]:
    """요약 데이터에서 핵심 기사만 필터링한다."""
    path = Path(summarized_path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    articles = data if isinstance(data, list) else data.get("articles", [])
    return [a for a in articles if a.get("tier", "핵심") == "핵심"]


def build_email_body(summarized_path: Path, today: str, dashboard_url: str) -> str:
    """이메일 본문(HTML)을 만든다. 오늘의 핵심 상위 3개 + 대시보드 링크 + 구독취소 안내."""
    core = _load_core_articles(summarized_path)
    highlights = step5_assemble.select_highlights(core, max_count=3) if core else []

    parts = [f"<h2>반도체 브리핑 · {html.escape(today)} 오늘의 핵심</h2>"]
    if not highlights:
        parts.append("<p>오늘은 핵심 기사가 없습니다. 전체 목록은 대시보드에서 확인해 주세요.</p>")
    else:
        parts.append("<ul>")
        for a in highlights:
            tag = html.escape(a.get("confirmation_tag") or "")
            title = html.escape(a.get("title", ""))
            url = html.escape(a.get("url", ""))
            summary = html.escape((a.get("summary") or "")[:200])
            parts.append(
                f'<li><a href="{url}">{tag} {title}</a><br>{summary}</li>'
            )
        parts.append("</ul>")

    parts.append(
        f'<p>전체 브리핑은 첨부 파일 또는 '
        f'<a href="{html.escape(dashboard_url)}">대시보드</a>에서 보실 수 있습니다.</p>'
    )
    parts.append(
        '<hr><p style="color:#888;font-size:12px">'
        "이 메일은 수신에 동의하신 분께만 발송됩니다. "
        "구독을 원치 않으시면 이 메일에 회신해 주세요.</p>"
    )
    return "".join(parts)
