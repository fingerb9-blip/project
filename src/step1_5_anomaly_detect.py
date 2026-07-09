"""Step 1.5. 이상 신호 감지 — 매시 정각 실행, 대시보드 즉시 속보 배너 갱신.

Phase 3 (docs/phase3_ipo.md) 기능 A. Step 1 수집 로직을 시간 단위로 재사용해
위험 키워드 언급 빈도가 최근 7일 같은 시간대 평균 대비 급증했는지 판정하고,
확정된 속보는 이메일이 아니라 대시보드(index.html) 즉시 재배포로 알린다.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from src import gemini_client, issue_tracking, notify, step0_init, step1_collect, step2_dedup, step5_assemble

logger = logging.getLogger(__name__)

_THRESHOLD_RATIO = 3.0
_COLD_START_MIN_COUNT = 3
_SUPPRESS_WINDOW_HOURS = 24
_KST = timezone(timedelta(hours=9))
_ROLLING_WINDOW_DAYS = 7

_CONFIRM_SCHEMA = {
    "type": "object",
    "properties": {
        "is_breaking": {"type": "boolean"},
        "tag": {"type": "string", "enum": ["[확정]", "[관측]"]},
        "headline": {"type": "string"},
    },
    "required": ["is_breaking", "tag", "headline"],
}


def match_risk_keywords(text: str, risk_keywords: list[str]) -> list[str]:
    """텍스트에서 매칭되는 위험 키워드를 반환한다."""
    return [kw for kw in risk_keywords if kw in text]


def count_entity_keyword_mentions(articles: list[dict], risk_keywords: list[str]) -> dict:
    """기업(entity) + 위험 키워드별 최근 1시간 언급 건수를 집계한다.

    Args:
        articles: companies 필드(정규화된 기업 id 리스트)가 포함된 기사 리스트
        risk_keywords: config/keywords.yaml의 risk_keywords

    Returns:
        {entity: {keyword: count}} 중첩 dict (매칭 없는 조합은 키 자체가 없음)
    """
    counts: dict[str, dict[str, int]] = {}
    for article in articles:
        text = f"{article.get('title', '')} {article.get('raw_text', '')}"
        matched_keywords = match_risk_keywords(text, risk_keywords)
        if not matched_keywords:
            continue
        for entity in article.get("companies", []):
            entity_counts = counts.setdefault(entity, {})
            for keyword in matched_keywords:
                entity_counts[keyword] = entity_counts.get(keyword, 0) + 1
    return counts


def get_baseline_avg(baseline: dict, entity: str, keyword: str, hour: int) -> float:
    """entity+keyword의 특정 시간대 이동평균을 조회한다. 없으면 0.0."""
    try:
        return baseline[entity][keyword]["hourly_avg_7d"][hour]
    except (KeyError, IndexError):
        return 0.0


def update_baseline_avg(baseline: dict, entity: str, keyword: str, hour: int, count: int) -> None:
    """entity+keyword의 특정 시간대 이동평균을 rolling update한다.

    최근 7일치 원본 카운트를 저장하지 않고, 지수이동평균으로 7일 평균을 근사한다:
    new_avg = old_avg + (count - old_avg) / 7
    """
    hourly = baseline.setdefault(entity, {}).setdefault(keyword, {}).setdefault(
        "hourly_avg_7d", [0.0] * 24
    )
    old_avg = hourly[hour]
    hourly[hour] = old_avg + (count - old_avg) / _ROLLING_WINDOW_DAYS


def detect_anomalies(counts: dict, baseline: dict, hour: int) -> list[dict]:
    """임계치(평시 대비 3배) 초과 entity+keyword 조합을 찾는다.

    baseline이 아직 없는 콜드 스타트 상황(avg == 0)에서는 오탐을 막기 위해
    최소 절대 건수(_COLD_START_MIN_COUNT) 이상일 때만 이상 신호로 본다.

    Args:
        counts: count_entity_keyword_mentions 결과
        baseline: frequency_baseline.json 로드 결과
        hour: 현재 시(0~23)

    Returns:
        {entity, keyword, count, avg, ratio} 리스트 (임계치 초과 순서 무관)
    """
    anomalies = []
    for entity, keyword_counts in counts.items():
        for keyword, count in keyword_counts.items():
            avg = get_baseline_avg(baseline, entity, keyword, hour)
            if avg > 0:
                ratio = count / avg
                if ratio >= _THRESHOLD_RATIO:
                    anomalies.append(
                        {"entity": entity, "keyword": keyword, "count": count, "avg": avg, "ratio": ratio}
                    )
            elif count >= _COLD_START_MIN_COUNT:
                anomalies.append(
                    {"entity": entity, "keyword": keyword, "count": count, "avg": avg, "ratio": float("inf")}
                )
    return anomalies


def make_anomaly_issue_id(entity: str, keyword: str, today: str) -> str:
    """entity+keyword+today로 결정적인 issue_id를 생성한다."""
    return hashlib.sha1(f"{entity}|{keyword}|{today}".encode("utf-8")).hexdigest()[:12]


def is_suppressed(issues: list[dict], issue_id: str, now_iso: str) -> bool:
    """같은 issue_id로 24시간 내 이미 속보를 띄웠으면 True (알림 피로 방지)."""
    issue = next((i for i in issues if i.get("issue_id") == issue_id), None)
    if issue is None or not issue.get("last_alerted_at"):
        return False
    last_alerted = datetime.fromisoformat(issue["last_alerted_at"])
    now = datetime.fromisoformat(now_iso)
    return now - last_alerted < timedelta(hours=_SUPPRESS_WINDOW_HOURS)


def confirm_breaking_news(entity: str, keyword: str, articles: list[dict]) -> dict:
    """Gemini API로 급증이 진짜 속보인지 단순 재탕 보도인지 사실관계를 확인한다.

    실패 시(API 에러) 알림 피로/오탐을 피하기 위해 fail-safe로 is_breaking=False를 반환한다.

    Args:
        entity: 정규화된 기업 id
        keyword: 매칭된 위험 키워드
        articles: 해당 entity+keyword에 매칭된 최근 1시간 기사 리스트

    Returns:
        {"is_breaking": bool, "tag": "[확정]"|"[관측]", "headline": str}
    """
    payload = [{"title": a.get("title", ""), "snippet": a.get("raw_text", "")[:300]} for a in articles]
    prompt = (
        f"'{entity}'와 관련해 위험 키워드 '{keyword}'가 최근 1시간 동안 평소보다 급증해서 언급됐다. "
        "아래 기사 목록을 보고 이것이 진짜 새로운 속보인지, 단순히 예전 보도를 재탕한 것인지 판단하라. "
        "진짜 속보라고 판단되면 is_breaking=true, 소스가 이미 확정적으로 발표한 사실이면 tag='[확정]', "
        "아직 확인되지 않은 정황이면 tag='[관측]'으로 표기하고, headline에 한 줄 속보 제목을 작성하라.\n\n"
        f"기사 목록: {json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        return gemini_client.call_gemini(prompt, _CONFIRM_SCHEMA, model=gemini_client.DEFAULT_MODEL)
    except RuntimeError as exc:
        logger.error("속보 사실 확인 실패, 안전하게 속보 아님으로 처리: %s", exc)
        return {"is_breaking": False, "tag": "[관측]", "headline": ""}


def _load_json(path: Path) -> dict:
    if not Path(path).exists():
        return {}
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run(
    feeds_config: dict,
    aliases_config: dict,
    risk_keywords: list[str],
    frequency_baseline_path: str,
    issues_path: str,
    dashboard_dir: str,
    state_path: str,
    today: str,
    hour: int,
    now_iso: str,
) -> list[dict]:
    """Step 1.5 진입점. 매시 정각 실행되어 이상 신호를 감지하고 확정 속보를 대시보드에 반영한다.

    확정 속보가 없으면 frequency_baseline.json만 갱신하고 대시보드는 건드리지 않는다
    (평시에 매시간 Pages 재배포가 발생하지 않도록 하기 위함).

    Args:
        feeds_config: sources/feeds.yaml 로드 결과
        aliases_config: config/company_aliases.yaml 로드 결과
        risk_keywords: config/keywords.yaml의 risk_keywords
        frequency_baseline_path: data/state/frequency_baseline.json 경로
        issues_path: data/state/issues.json 경로
        dashboard_dir: data/dashboard 디렉토리 경로
        state_path: data/state/run_status.json 경로 (index.html 상태 배지용)
        today: YYYY-MM-DD 형식 날짜 문자열
        hour: 현재 시(0~23, KST 등 프로젝트 기준 시간대)
        now_iso: 현재 시각 ISO8601 문자열 (알림 억제 판정 및 last_alerted_at 기록용)

    Returns:
        이번 실행에서 새로 확정된 속보(issue) 리스트
    """
    since = datetime.fromisoformat(now_iso) - timedelta(hours=1)
    rss_articles = step1_collect.fetch_rss_articles(feeds_config.get("feeds") or [], since)
    articles = step2_dedup.normalize_company_names(rss_articles, aliases_config)

    counts = count_entity_keyword_mentions(articles, risk_keywords)
    baseline = _load_json(frequency_baseline_path)
    anomalies = detect_anomalies(counts, baseline, hour)

    issues = issue_tracking.load_issues(issues_path)
    confirmed_alerts = []

    for anomaly_entry in anomalies:
        entity, keyword = anomaly_entry["entity"], anomaly_entry["keyword"]
        issue_id = make_anomaly_issue_id(entity, keyword, today)
        if is_suppressed(issues, issue_id, now_iso):
            continue

        matched_articles = [
            a
            for a in articles
            if entity in a.get("companies", [])
            and keyword in match_risk_keywords(f"{a.get('title', '')} {a.get('raw_text', '')}", [keyword])
        ]
        result = confirm_breaking_news(entity, keyword, matched_articles)
        if not result.get("is_breaking"):
            continue

        entity_name = issue_tracking.entity_display_name(entity, aliases_config)
        issue = issue_tracking.find_issue(issues, issue_id)
        if issue is None:
            issue = {
                "issue_id": issue_id,
                "entity": entity_name,
                "title": result.get("headline") or f"{entity_name} {keyword} 관련 속보",
                "first_seen": today,
                "related_article_ids": [],
            }
            issues.append(issue)

        issue["last_updated"] = today
        issue["status"] = "진행중"
        issue["headline"] = result.get("headline") or issue.get("title", "")
        issue["tag"] = result.get("tag", "[관측]")
        issue["last_alerted_at"] = now_iso
        issue["related_article_ids"] = sorted(
            set(issue.get("related_article_ids", [])) | {a["id"] for a in matched_articles}
        )
        confirmed_alerts.append(issue)

    for entity, keyword_counts in counts.items():
        for keyword, count in keyword_counts.items():
            update_baseline_avg(baseline, entity, keyword, hour, count)

    _save_json(frequency_baseline_path, baseline)
    issue_tracking.save_issues(issues_path, issues)

    if confirmed_alerts:
        dashboard_dir = Path(dashboard_dir)
        alerts_dir = dashboard_dir / "alerts"
        alerts_dir.mkdir(parents=True, exist_ok=True)
        for issue in confirmed_alerts:
            detail_html = step5_assemble.build_alert_detail_html(issue)
            (alerts_dir / f"{issue['issue_id']}.html").write_text(detail_html, encoding="utf-8")

        pending_path = Path(issues_path).parent.parent.parent / "config" / "keywords_pending.yaml"
        index_html = step5_assemble.build_index_html(
            dashboard_dir,
            Path(state_path),
            issues_path=Path(issues_path),
            now=now_iso,
            radar_data=step5_assemble.load_latest_radar(dashboard_dir.parent / "radar"),
            pending_keywords=step5_assemble.load_pending_keywords(pending_path),
        )
        (dashboard_dir / "index.html").write_text(index_html, encoding="utf-8")

    return confirmed_alerts


def main() -> None:
    """독립 실행 진입점. GitHub Actions hourly_anomaly_check.yml에서 매시 정각 호출한다."""
    load_dotenv()
    base_dir = Path(__file__).resolve().parent.parent
    now_utc = datetime.now(timezone.utc)
    today = now_utc.astimezone(_KST).date().isoformat()

    config = step0_init.load_configs(base_dir / "config", base_dir / "sources" / "feeds.yaml")
    paths = step0_init.prepare_today_paths(base_dir, today)

    try:
        run(
            feeds_config=config["feeds"],
            aliases_config=config["company_aliases"],
            risk_keywords=config["keywords"].get("risk_keywords", []),
            frequency_baseline_path=paths["frequency_baseline"],
            issues_path=paths["issues"],
            dashboard_dir=paths["dashboard_dir"],
            state_path=paths["state"],
            today=today,
            hour=now_utc.hour,
            now_iso=now_utc.isoformat(),
        )
    except Exception as exc:
        notify.notify_failure("이상 신호 감지 실행 실패", f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
