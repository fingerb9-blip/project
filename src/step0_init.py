"""Step 0. 시작 — 설정 로드 및 검증."""

from pathlib import Path


def load_configs(config_dir: Path, sources_path: Path) -> dict:
    """config/*.yaml, sources/feeds.yaml을 로드하고 스키마를 검증한다.

    Args:
        config_dir: config/ 디렉토리 경로
        sources_path: sources/feeds.yaml 경로

    Returns:
        검증된 설정 객체 (다음 Step에 전달)

    Raises:
        ValueError: 스키마 검증 실패 시
    """
    # TODO: yaml 파싱 + 스키마 검증
    raise NotImplementedError


def prepare_today_paths(base_dir: Path, today: str) -> dict:
    """오늘 날짜 기준 data/*/YYYY-MM-DD.json 경로를 생성한다.

    Args:
        base_dir: 프로젝트 루트 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        Step별 출력 경로 dict
    """
    # TODO: data/raw, dedup, classified, summarized, archive 경로 생성
    raise NotImplementedError


def run(today: str) -> dict:
    """Step 0 진입점. 파싱 실패 시 notify.py로 알림 발송 후 즉시 중단한다.

    Args:
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        검증된 설정 객체
    """
    # TODO: load_configs 실패 시 notify.notify_failure() 호출 후 중단
    raise NotImplementedError
