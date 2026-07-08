"""Step 6. 저장 확인 — 대시보드 산출물이 정상 생성됐는지 확인한다."""

import logging
from pathlib import Path

from src import notify

logger = logging.getLogger(__name__)


def run(dashboard_dir: str, today: str) -> bool:
    """Step 6 진입점. 08:30까지 대시보드가 갱신되지 않으면 실패 알림을 발송한다
    ("뉴스 없는 날"과 구분).

    Args:
        dashboard_dir: data/dashboard 디렉토리 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        대시보드 산출물 정상 생성 여부 (호출자가 run_status.json에 실제 결과를 반영할 수 있도록)
    """
    dashboard_dir = Path(dashboard_dir)
    daily_html = dashboard_dir / f"{today}.html"
    index_html = dashboard_dir / "index.html"

    missing = [p for p in (daily_html, index_html) if not p.exists()]
    if missing:
        notify.notify_failure(
            "08:30까지 대시보드 미갱신",
            f"대시보드 파일이 생성되지 않았습니다: {', '.join(str(p) for p in missing)}",
        )
        return False

    return True
