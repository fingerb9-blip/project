"""실패 알림 공통 모듈."""

import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _send_admin_email(subject: str, message: str) -> None:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    to_addr = os.environ.get("SMTP_TO")

    if not all([host, user, password, to_addr]):
        logger.warning("SMTP 설정이 없어 알림 이메일을 보내지 못했습니다: %s", subject)
        return

    msg = MIMEText(message, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


def notify_failure(subject: str, message: str) -> None:
    """관리자 이메일로 실패 알림을 발송한다.

    설정 로드 실패, 08:30까지 미완료 등 파이프라인 중단 상황에서 호출된다.

    Args:
        subject: 알림 제목 (예: "설정 로드 실패", "08:30 발송 미완료")
        message: 알림 본문
    """
    logger.error("[FAILURE] %s: %s", subject, message)
    _send_admin_email(f"[반도체 브리핑 실패] {subject}", message)


def notify_warning(subject: str, message: str) -> None:
    """파이프라인은 계속 진행하되 경고 알림을 발송한다.

    소스 0건이 최근 7일 평균 대비 이례적으로 지속되는 "조용한 품질 열화" 상황에 사용한다.
    단순 접속 재시도 실패처럼 매일 있을 수 있는 일은 각 모듈에서 logging으로만 남기고
    이 함수를 호출하지 않는다.

    Args:
        subject: 경고 제목
        message: 경고 본문
    """
    logger.warning("[WARNING] %s: %s", subject, message)
    _send_admin_email(f"[반도체 브리핑 경고] {subject}", message)
