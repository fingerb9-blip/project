"""데일리 브리핑 워치독 — 예약 실행이 시작조차 못 한 경우를 감지한다.

daily_briefing.yml의 "Notify on failure" 스텝은 그 워크플로우의 잡이 러너를 배정받아
최소 한 스텝이라도 실행돼야 발동한다. GitHub Actions 인프라 문제로 러너 배정 자체가
안 되면 잡이 "cancelled"로 끝나고 어떤 스텝도 실행되지 않아, 그 실패 알림 스텝도 건너뛰게
된다 — 아무 알림 없이 그날 브리핑이 조용히 빠지는 침묵 실패다. 이 스크립트는 별도
워치독 워크플로우(daily_briefing_watchdog.yml)에서 매일 목표 시각보다 늦게 실행돼
run_status.json을 점검함으로써 그 공백을 메운다.

Usage:
    python scripts/check_daily_run_freshness.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src import notify, run_status  # noqa: E402

_KST = timezone(timedelta(hours=9))


def run(status: dict | None, today: str) -> bool:
    """오늘 날짜로 성공한 daily-briefing 실행이 있는지 확인하고, 없으면 실패 알림을 보낸다.

    Args:
        status: run_status.json 로드 결과 (없으면 None)
        today: KST 기준 오늘 날짜 (YYYY-MM-DD)

    Returns:
        오늘 성공 실행이 확인되면 True, 아니면 False(알림 발송됨)
    """
    if run_status.is_duplicate_run(status, today):
        return True

    last_run_date = status.get("last_run_date") if status else None
    last_run_status = status.get("last_run_status") if status else None
    notify.notify_failure(
        "오늘 데일리 브리핑 실행 확인 안 됨",
        f"{today} 기준 성공한 daily-briefing 실행이 없습니다 "
        f"(last_run_date={last_run_date}, last_run_status={last_run_status}). "
        "GitHub Actions 예약 실행이 러너 배정 실패 등으로 시작조차 못 했을 수 있습니다 — "
        "Actions 탭에서 daily-briefing을 확인하고 필요하면 수동 재실행(workflow_dispatch)하세요.",
    )
    return False


def main() -> int:
    status = run_status.load_status(BASE_DIR / "data" / "state" / "run_status.json")
    today = datetime.now(_KST).date().isoformat()

    if run(status, today):
        print(f"OK: {today} 실행 성공 확인됨")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
