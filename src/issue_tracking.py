"""이슈 타임라인 저장소(issues.json) 읽기/쓰기.

Phase 3의 이상 신호 감지(step1_5)와 이슈 지식그래프(step4_5)가 공유하는
data/state/issues.json을 다룬다.
"""

import json
from pathlib import Path


def load_issues(path: Path) -> list[dict]:
    """issues.json을 읽는다. 파일이 없으면 빈 리스트를 반환한다."""
    if not Path(path).exists():
        return []
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def save_issues(path: Path, issues: list[dict]) -> None:
    """issues.json에 이슈 타임라인을 저장한다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(issues, f, ensure_ascii=False, indent=2)


def entity_display_name(entity_id: str, aliases_config: dict) -> str:
    """정규화된 기업 id를 company_aliases.yaml의 대표 표기(첫 alias)로 변환한다."""
    aliases = aliases_config.get(entity_id, {}).get("aliases") or [entity_id]
    return aliases[0]


def find_issue(issues: list[dict], issue_id: str) -> dict | None:
    """issue_id로 이슈를 찾는다. 없으면 None."""
    return next((i for i in issues if i.get("issue_id") == issue_id), None)
