"""실패 알림 공통 모듈."""


def notify_failure(subject: str, message: str) -> None:
    """관리자 이메일로 실패 알림을 발송한다.

    설정 로드 실패, 08:30까지 미완료 등 파이프라인 중단 상황에서 호출된다.

    Args:
        subject: 알림 제목 (예: "설정 로드 실패", "08:30 발송 미완료")
        message: 알림 본문
    """
    # TODO: SMTP로 관리자 이메일 발송
    raise NotImplementedError


def notify_warning(subject: str, message: str) -> None:
    """파이프라인은 계속 진행하되 경고성 알림을 발송한다.

    소스 3회 연속 0건, 특정 소스 재시도 최종 실패 등에 사용한다.

    Args:
        subject: 경고 제목
        message: 경고 본문
    """
    # TODO: 로그 기록 + (선택) 경고 이메일 발송
    raise NotImplementedError
