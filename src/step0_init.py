"""Step 0. 시작 — 설정 로드 및 검증."""

import os
from pathlib import Path

import yaml

from src import notify, run_status

REQUIRED_CONFIG_FILES = [
    "company_aliases.yaml",
    "categories.yaml",
    "keywords.yaml",
    "source_tiers.yaml",
]


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"{path} 이 비어 있습니다")
    return data


def load_configs(config_dir: Path, sources_path: Path) -> dict:
    """config/*.yaml, sources/feeds.yaml을 로드하고 스키마를 검증한다.

    Args:
        config_dir: config/ 디렉토리 경로
        sources_path: sources/feeds.yaml 경로

    Returns:
        검증된 설정 객체 (다음 Step에 전달)

    Raises:
        ValueError: 필수 파일 누락 또는 파싱 실패 시
    """
    configs = {}
    for filename in REQUIRED_CONFIG_FILES:
        path = config_dir / filename
        if not path.exists():
            raise ValueError(f"필수 설정 파일이 없습니다: {path}")
        key = filename[: -len(".yaml")]
        configs[key] = _load_yaml(path)

    if not sources_path.exists():
        raise ValueError(f"소스 목록 파일이 없습니다: {sources_path}")
    configs["feeds"] = _load_yaml(sources_path)

    return configs


class DuplicateRunError(Exception):
    """오늘 날짜로 이미 성공 처리된 실행이 있어 중복 실행을 방지할 때 발생한다."""


def prepare_today_paths(base_dir: Path, today: str) -> dict:
    """오늘 날짜 기준 data/*/YYYY-MM-DD.json 경로를 생성한다.

    Args:
        base_dir: 프로젝트 루트 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        Step별 출력 경로 dict
    """
    paths = {
        "raw": base_dir / "data" / "raw" / f"{today}.json",
        "dedup": base_dir / "data" / "dedup" / f"{today}.json",
        "classified": base_dir / "data" / "classified" / f"{today}.json",
        "summarized": base_dir / "data" / "summarized" / f"{today}.json",
        "archive": base_dir / "data" / "archive" / f"{today}.md",
        "dashboard_dir": base_dir / "data" / "dashboard",
        "state": base_dir / "data" / "state" / "run_status.json",
    }
    for key, path in paths.items():
        if key == "dashboard_dir":
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
    return paths


def check_duplicate_run(state_path: Path, today: str) -> None:
    """오늘 날짜로 이미 성공 처리된 실행이 있으면 중단시킨다.

    수동 `workflow_dispatch` 재실행 실수를 대비한 가드다. 환경변수
    `FORCE_RUN=true`를 설정하면(의도적 재실행·테스트) 이 검사를 건너뛴다.

    Args:
        state_path: data/state/run_status.json 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Raises:
        DuplicateRunError: 오늘 이미 성공 실행된 이력이 있고 FORCE_RUN이 아닐 때
    """
    if os.environ.get("FORCE_RUN", "").strip().lower() == "true":
        return
    status = run_status.load_status(state_path)
    if run_status.is_duplicate_run(status, today):
        raise DuplicateRunError(
            f"{today} 실행이 이미 성공 처리되었습니다 (중복 실행 방지). "
            "의도된 재실행이면 FORCE_RUN=true로 설정하세요."
        )


def run(today: str) -> dict:
    """Step 0 진입점. 파싱 실패 시 notify.py로 알림 발송 후 즉시 중단한다.

    Args:
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        검증된 설정 객체 (config["paths"]에 Step별 출력 경로 포함)
    """
    base_dir = Path(__file__).resolve().parent.parent
    try:
        config = load_configs(base_dir / "config", base_dir / "sources" / "feeds.yaml")
        config["paths"] = prepare_today_paths(base_dir, today)
    except (ValueError, yaml.YAMLError) as exc:
        notify.notify_failure("설정 로드 실패", str(exc))
        raise

    check_duplicate_run(config["paths"]["state"], today)
    return config
