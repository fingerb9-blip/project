"""Step 7. 이메일 뉴스레터 — 명단 구독자에게 그날 브리핑을 발송한다 (무료, 지인 대상)."""

import html
import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
    if _STYLE_LINK not in html_text:
        logger.warning(
            "대시보드 HTML에서 스타일 링크(%s)를 찾지 못해 CSS를 인라인하지 못했습니다. "
            "이메일 첨부가 스타일 없이 발송될 수 있습니다",
            _STYLE_LINK,
        )
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
            # javascript: 등 위험한 스킴 차단 — step5_assemble._safe_url()이 http/https만
            # 허용하고 이미 이스케이프된 URL(또는 None)을 반환한다. 여기서 다시 escape하지 않는다.
            safe_url = step5_assemble._safe_url(a.get("url", ""))
            summary = html.escape((a.get("summary") or "")[:200])
            if safe_url:
                parts.append(
                    f'<li><a href="{safe_url}">{tag} {title}</a><br>{summary}</li>'
                )
            else:
                parts.append(f"<li>{tag} {title}<br>{summary}</li>")
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


def _send_html_email(
    to_addr: str, subject: str, html_body: str, attachment_name: str, attachment_html: str
) -> None:
    """HTML 본문 + HTML 첨부 1개를 SMTP로 발송한다. 실패 시 예외를 던진다."""
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    if not all([host, user, password]):
        raise RuntimeError("SMTP 설정(SMTP_HOST/USER/PASSWORD)이 없습니다")

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", _charset="utf-8"))

    attachment = MIMEText(attachment_html, "html", _charset="utf-8")
    attachment.add_header("Content-Disposition", "attachment", filename=attachment_name)
    msg.attach(attachment)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


def _redact_email(addr: str) -> str:
    """이메일 주소를 로그용으로 마스킹한다.

    로컬 파트(@ 앞부분)의 첫 글자만 남기고 나머지는 '***'로 치환한다.
    '@'가 없거나 빈 문자열이면 통째로 '***'를 반환한다.

    예: "alice@x.com" -> "a***@x.com", "b@y.com" -> "b***@y.com".
    """
    if not addr or "@" not in addr:
        return "***"
    local, _, domain = addr.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def load_send_state(state_path: Path) -> dict:
    """발송 상태를 로드한다."""
    path = Path(state_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save_send_state(state_path: Path, today: str, sent_count: int) -> None:
    """발송 상태를 저장한다."""
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"last_sent_date": today, "sent_count": sent_count}, ensure_ascii=False),
        encoding="utf-8",
    )


def run(
    dashboard_dir,
    summarized_path,
    state_path,
    today: str,
    dashboard_url: str,
    subscribers: list[str] | None = None,
) -> dict:
    """Step 7 진입점. 명단 구독자에게 그날 브리핑을 발송한다. 예외를 밖으로 던지지 않는다.

    Returns:
        {"sent": 성공 건수, "failed": 실패 건수, "skipped": 이번에 발송을 건너뛰었는지}
    """
    result = {"sent": 0, "failed": 0, "skipped": False}
    try:
        force = os.environ.get("FORCE_RESEND", "").strip().lower() == "true"
        if not force and load_send_state(state_path).get("last_sent_date") == today:
            logger.info("오늘(%s) 이미 발송함, 스킵", today)
            result["skipped"] = True
            return result

        if subscribers is None:
            subscribers = load_subscribers()
        if not subscribers:
            logger.info("구독자 명단이 비어 있어 발송하지 않습니다")
            return result

        subject = f"[반도체 브리핑] {today} 오늘의 핵심"
        body = build_email_body(Path(summarized_path), today, dashboard_url)
        attachment_html = build_standalone_html(Path(dashboard_dir), today)
        attachment_name = f"반도체브리핑_{today}.html"

        for addr in subscribers:
            try:
                _send_html_email(addr, subject, body, attachment_name, attachment_html)
                result["sent"] += 1
            except Exception as exc:  # noqa: BLE001 - 건별 실패는 로그 후 계속
                logger.error("구독자 %s 발송 실패: %s", _redact_email(addr), exc)
                result["failed"] += 1

        if result["sent"] > 0:
            save_send_state(state_path, today, result["sent"])
    except Exception as exc:  # noqa: BLE001 - Step 7 실패가 파이프라인을 막지 않도록 흡수
        logger.error("뉴스레터 발송 중 예기치 못한 오류(무시하고 계속): %s", exc)
    return result
