"""Step 6. 발송·저장 — Gmail SMTP 발송 및 아카이브."""


def send_email(briefing_md: str, smtp_config: dict) -> bool:
    """Gmail SMTP로 브리핑 문서를 발송한다.

    Args:
        briefing_md: Step 5 결과 브리핑 문서
        smtp_config: .env에서 로드한 SMTP 계정 정보

    Returns:
        발송 성공 여부
    """
    # TODO: smtplib로 발송
    raise NotImplementedError


def run(briefing_path: str, smtp_config: dict) -> None:
    """Step 6 진입점. 08:30까지 미완료 시 실패 알림을 발송한다("뉴스 없는 날"과 구분).

    Args:
        briefing_path: data/archive/YYYY-MM-DD.md 경로
        smtp_config: .env에서 로드한 SMTP 계정 정보
    """
    # TODO: send_email 실패 시 notify.notify_failure() 호출
    raise NotImplementedError
