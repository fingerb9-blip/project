"""Step 0. 시작 — 설정 로드 및 검증."""

from pathlib import Path

import yaml

from src import notify

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
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    return paths


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
        return config
    except (ValueError, yaml.YAMLError) as exc:
        notify.notify_failure("설정 로드 실패", str(exc))
        raise
