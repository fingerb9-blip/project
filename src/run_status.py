"""실행 상태 파일(run_status.json) 읽기/쓰기.

Phase 2에서 중복 실행 방지, 마지막 성공 시각 추적, "뉴스 없는 날"과
"파이프라인 실패"를 구분하기 위해 사용한다.
"""

import json
from pathlib import Path


def load_status(path: Path) -> dict | None:
    """run_status.json을 읽는다. 파일이 없으면 None을 반환한다."""
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_status(path: Path, status: dict) -> None:
    """run_status.json에 실행 상태를 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def is_duplicate_run(status: dict | None, today: str) -> bool:
    """오늘 날짜로 이미 성공 처리된 실행이 있는지 확인한다."""
    if status is None:
        return False
    return status.get("last_run_date") == today and status.get("last_run_status") == "success"
