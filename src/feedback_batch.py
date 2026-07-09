"""주간 배치 — feedback_queue.json을 모아 공통 키워드 후보를 keywords_pending.yaml에 반영한다."""

import json
import logging
from pathlib import Path

import yaml

from src import gemini_client

logger = logging.getLogger(__name__)

_KEYWORD_SCHEMA = {
    "type": "object",
    "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
    "required": ["keywords"],
}

_PRIORITY_THRESHOLD = 3


def load_queue(queue_path) -> list[dict]:
    """feedback_queue.json을 로드한다. 파일이 없으면 빈 리스트를 반환한다."""
    queue_path = Path(queue_path)
    if not queue_path.exists():
        return []
    with queue_path.open(encoding="utf-8") as f:
        return json.load(f)


def extract_common_keywords(flagged_articles: list[dict]) -> list[str]:
    """Gemini API(Flash-Lite)로 신고된 기사들에서 반복되는 공통 키워드를 추출한다.

    실패 시 사람이 직접 판단할 수 있도록 신고된 기사 제목을 그대로 후보로 반환한다
    (Step 4 요약 실패 시 헤드라인 폴백과 동일한 원칙).

    Args:
        flagged_articles: {title, ...} 형태의 신고된 기사 정보 리스트

    Returns:
        추출된 공통 키워드 문자열 리스트
    """
    titles = [a.get("title", "") for a in flagged_articles if a.get("title")]
    if not titles:
        return []

    prompt = (
        "다음은 사용자가 '노이즈'로 신고한 반도체 뉴스 기사 제목 목록이다. "
        "이 기사들에서 반복적으로 나타나는 공통 키워드(향후 블랙리스트 후보)를 추출해 "
        f"keywords 배열로 반환하라.\n\n제목 목록: {json.dumps(titles, ensure_ascii=False)}"
    )
    try:
        result = gemini_client.call_gemini(prompt, _KEYWORD_SCHEMA, model=gemini_client.LITE_MODEL)
        return list(result.get("keywords", []))
    except RuntimeError as exc:
        logger.error("공통 키워드 추출 실패, 신고 제목을 그대로 후보로 사용: %s", exc)
        return titles


def _count_keyword_matches(keyword: str, titles: list[str]) -> int:
    """키워드가 신고된 기사 제목들에 부분 문자열로 몇 번 등장하는지 센다."""
    return sum(1 for title in titles if keyword in title)


def load_pending(pending_path) -> dict:
    """config/keywords_pending.yaml을 로드한다. 파일이 없으면 빈 후보 목록을 반환한다."""
    pending_path = Path(pending_path)
    if not pending_path.exists():
        return {"candidates": []}
    with pending_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {"candidates": []}


def merge_candidates(pending: dict, keyword_counts: dict[str, int], batch_at: str) -> dict:
    """새 키워드 후보를 기존 대기열에 병합한다. 이미 있으면 신고 횟수를 실제 매칭 건수만큼 늘린다.

    동일 키워드가 report_count >= 3(임계치)이 되면 priority=True로 표시해
    주 1회 표본 검토에서 우선순위를 높인다.

    Args:
        pending: load_pending() 결과
        keyword_counts: {키워드: 이번 배치에서 실제 매칭된 기사 건수} (run()에서
            _count_keyword_matches()로 계산)
        batch_at: 이번 배치 실행 시각 (ISO8601)

    Returns:
        갱신된 pending dict
    """
    by_keyword = {c["keyword"]: c for c in pending.get("candidates", [])}

    for keyword, count in keyword_counts.items():
        if keyword in by_keyword:
            by_keyword[keyword]["report_count"] += count
            by_keyword[keyword]["last_flagged_at"] = batch_at
        else:
            by_keyword[keyword] = {
                "keyword": keyword,
                "report_count": count,
                "first_flagged_at": batch_at,
                "last_flagged_at": batch_at,
                "priority": False,
            }
        by_keyword[keyword]["priority"] = by_keyword[keyword]["report_count"] >= _PRIORITY_THRESHOLD

    return {"candidates": list(by_keyword.values())}


def run(queue_path: str, pending_path: str, batch_at: str) -> dict:
    """배치 진입점. 큐를 처리해 keywords_pending.yaml을 갱신하고 큐를 비운다.

    Args:
        queue_path: data/state/feedback_queue.json 경로
        pending_path: config/keywords_pending.yaml 경로
        batch_at: 배치 실행 시각 (ISO8601)

    Returns:
        갱신된 pending dict
    """
    queue_path = Path(queue_path)
    pending_path = Path(pending_path)

    flagged_articles = load_queue(queue_path)
    new_keywords = extract_common_keywords(flagged_articles)
    titles = [a.get("title", "") for a in flagged_articles if a.get("title")]
    keyword_counts = {
        keyword: max(1, _count_keyword_matches(keyword, titles)) for keyword in new_keywords
    }

    pending = load_pending(pending_path)
    updated = merge_candidates(pending, keyword_counts, batch_at)

    pending_path.parent.mkdir(parents=True, exist_ok=True)
    with pending_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(updated, f, allow_unicode=True, sort_keys=False)

    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("w", encoding="utf-8") as f:
        json.dump([], f)

    return updated


def main() -> None:
    """독립 실행 진입점. GitHub Actions weekly_feedback_batch.yml에서 주 1회 호출한다."""
    from datetime import datetime, timezone

    from dotenv import load_dotenv

    load_dotenv()
    base_dir = Path(__file__).resolve().parent.parent
    run(
        str(base_dir / "data" / "state" / "feedback_queue.json"),
        str(base_dir / "config" / "keywords_pending.yaml"),
        datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    main()
