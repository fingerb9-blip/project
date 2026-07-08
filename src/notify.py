"""실패 알림 공통 모듈."""

import argparse
import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_AUTH_ERROR_MARKERS = (
    "401",
    "403",
    "UNAUTHENTICATED",
    "PERMISSION_DENIED",
    "Unauthorized",
    "API key not valid",
    "invalid_api_key",
)


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

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        # 알림 메일 전송 자체가 실패해도 원래 파이프라인 예외를 가리면 안 되므로 여기서 흡수한다.
        logger.error("알림 이메일 발송 실패: %s (원래 알림: %s)", exc, subject)


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


def looks_like_auth_error(exc: BaseException) -> bool:
    """예외가 인증/Secrets 관련 오류로 보이는지 판별한다.

    필수 환경변수(Secrets) 누락은 KeyError로, SMTP 인증 실패는
    smtplib.SMTPAuthenticationError로 나타난다. Gemini API 401/403 오류는
    gemini_client.call_gemini()가 RuntimeError로 래핑하므로 메시지 내 키워드로 판별한다.

    Args:
        exc: 파이프라인에서 발생한 예외

    Returns:
        인증/Secrets 문제로 추정되면 True
    """
    if isinstance(exc, (KeyError, smtplib.SMTPAuthenticationError)):
        return True
    text = str(exc)
    return any(marker in text for marker in _AUTH_ERROR_MARKERS)


def notify_auth_error(context: str, detail: str) -> None:
    """인증 오류(SMTP/Gemini 401·403, Secrets 누락 등) 전용 알림을 발송한다.

    Args:
        context: 오류가 발생한 맥락 (예: "파이프라인 실행 중 인증 오류")
        detail: 오류 상세 내용
    """
    subject = "인증 오류 — Secrets 재확인 필요"
    message = (
        f"{context}\n\n{detail}\n\n"
        "GEMINI_API_KEY, SMTP_USER, SMTP_APP_PASSWORD 등 GitHub Secrets가 "
        "만료되었거나 잘못 등록되지 않았는지 확인하세요."
    )
    logger.error("[AUTH_ERROR] %s: %s", context, detail)
    _send_admin_email(f"[반도체 브리핑 인증 오류] {subject}", message)


def _cli_main(argv: list[str] | None = None) -> None:
    """GitHub Actions 워크플로우 자체 실패 시 독립 호출되는 CLI 진입점.

    `main.py` 실행 도중의 예외는 main.py 자신이 notify_failure/notify_auth_error를
    직접 호출한다. 이 CLI는 러너 오류·타임아웃처럼 main.py 밖에서 잡을 수 없는
    워크플로우 실패를 위한 이중 알림 경로다(명세서 4장 "이중화" 원칙).
    """
    parser = argparse.ArgumentParser(description="워크플로우 실패 알림 발송")
    parser.add_argument("--event", required=True, choices=["pipeline_failed", "auth_error"])
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)

    run_id_note = f"\n\nGitHub Actions Run ID: {args.run_id}" if args.run_id else ""
    if args.event == "auth_error":
        notify_auth_error(
            "GitHub Actions 워크플로우 인증 오류",
            f"daily-briefing 워크플로우가 인증 오류로 실패했습니다.{run_id_note}",
        )
    else:
        notify_failure(
            "GitHub Actions 워크플로우 실패",
            f"daily-briefing 워크플로우 실행이 실패했습니다. 실행 로그를 확인하세요.{run_id_note}",
        )


if __name__ == "__main__":
    _cli_main()
