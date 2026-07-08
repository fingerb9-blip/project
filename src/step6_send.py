"""Step 6. 발송·저장 — Gmail SMTP 발송 및 아카이브."""

import logging
import smtplib
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path

from src import notify

logger = logging.getLogger(__name__)


def send_email(briefing_md: str, smtp_config: dict) -> bool:
    """Gmail SMTP로 브리핑 문서를 발송한다.

    Args:
        briefing_md: Step 5 결과 브리핑 문서
        smtp_config: {"host", "port", "user", "password", "to"} 형태의 SMTP 계정 정보

    Returns:
        발송 성공 여부
    """
    msg = MIMEText(briefing_md, _charset="utf-8")
    msg["Subject"] = f"[반도체 뉴스 브리핑] {date.today().isoformat()}"
    msg["From"] = smtp_config["user"]
    msg["To"] = smtp_config["to"]

    try:
        with smtplib.SMTP(smtp_config["host"], int(smtp_config["port"])) as server:
            server.starttls()
            server.login(smtp_config["user"], smtp_config["password"])
            server.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("Gmail SMTP 발송 실패: %s", exc)
        return False


def run(briefing_path: str, smtp_config: dict) -> bool:
    """Step 6 진입점. 08:30까지 미완료 시 실패 알림을 발송한다("뉴스 없는 날"과 구분).

    Args:
        briefing_path: data/archive/YYYY-MM-DD.md 경로
        smtp_config: {"host", "port", "user", "password", "to"} 형태의 SMTP 계정 정보

    Returns:
        발송 성공 여부 (호출자가 run_status.json에 실제 결과를 반영할 수 있도록)
    """
    briefing_path = Path(briefing_path)
    if not briefing_path.exists():
        notify.notify_failure("08:30 발송 미완료", f"브리핑 파일이 없습니다: {briefing_path}")
        return False

    briefing_md = briefing_path.read_text(encoding="utf-8")
    if not send_email(briefing_md, smtp_config):
        notify.notify_failure("08:30 발송 미완료", "Gmail SMTP 발송 실패")
        return False

    return True
