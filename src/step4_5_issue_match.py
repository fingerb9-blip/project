"""Step 4.5. 이슈 지식그래프 — 반복 이슈 추적 & 경과 요약.

Phase 3 (docs/phase3_ipo.md) 기능 B. Step 4 요약 이후, Step 5 조립 이전에 실행되어
오늘 요약된 "핵심" 기사를 기존 진행 중 이슈와 매칭하거나 새 이슈로 만든다.
3일 이상 지속된 이슈는 경과 요약 문단을 생성하고, 7일 이상 갱신이 없으면 종료 처리한다.
"""

import hashlib
import json
import logging
from datetime import date
from pathlib import Path

from src import gemini_client, issue_tracking

logger = logging.getLogger(__name__)

_PROGRESS_SUMMARY_MIN_DAYS = 3
_CLOSE_AFTER_DAYS = 7
_SNIPPET_LEN = 300
# 실제 응답 품질 비교 전까지는 DEFAULT_MODEL(Flash) 유지. 검증 후 LITE_MODEL로 바꿀 때 이 한 줄만 수정하면 된다.
_PROGRESS_SUMMARY_MODEL = gemini_client.DEFAULT_MODEL

_MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "article_id": {"type": "string"},
                    "issue_id": {"type": "string"},
                },
                "required": ["article_id", "issue_id"],
            },
        }
    },
    "required": ["matches"],
}

_PROGRESS_SCHEMA = {
    "type": "object",
    "properties": {"progress_summary": {"type": "string"}},
    "required": ["progress_summary"],
}


def create_issue(article: dict, today: str, aliases_config: dict) -> dict:
    """오늘 요약된 기사에서 새 이슈를 생성한다.

    Args:
        article: Step 4 요약 결과 기사 dict (companies 필드 포함)
        today: YYYY-MM-DD 형식 날짜 문자열
        aliases_config: config/company_aliases.yaml 로드 결과

    Returns:
        신규 이슈 dict
    """
    companies = article.get("companies") or []
    entity = issue_tracking.entity_display_name(companies[0], aliases_config) if companies else "미상"
    issue_id = hashlib.sha1(f"{entity}|{article['title']}|{today}".encode("utf-8")).hexdigest()[:12]
    return {
        "issue_id": issue_id,
        "entity": entity,
        "title": article["title"],
        "first_seen": today,
        "last_updated": today,
        "status": "진행중",
        "related_article_ids": [article["id"]],
    }


def apply_match(issue: dict, article: dict, today: str) -> None:
    """매칭된 기사를 기존 이슈에 연결하고 last_updated를 갱신한다."""
    ids = list(dict.fromkeys([*issue.get("related_article_ids", []), article["id"]]))
    issue["related_article_ids"] = ids
    issue["last_updated"] = today


def days_active(issue: dict, today: str) -> int:
    """이슈가 최초 감지된 이후 경과한 일수."""
    return (date.fromisoformat(today) - date.fromisoformat(issue["first_seen"])).days


def needs_progress_summary(issue: dict, today: str) -> bool:
    """이슈가 3일 이상 지속됐는지 판정한다."""
    return days_active(issue, today) >= _PROGRESS_SUMMARY_MIN_DAYS


def close_stale_issues(issues: list[dict], today: str) -> None:
    """last_updated 기준 7일 이상 갱신 없는 진행중 이슈를 종료 처리한다."""
    for issue in issues:
        if issue.get("status") != "진행중":
            continue
        idle_days = (date.fromisoformat(today) - date.fromisoformat(issue["last_updated"])).days
        if idle_days >= _CLOSE_AFTER_DAYS:
            issue["status"] = "종료"


def match_articles_to_issues(articles: list[dict], active_issues: list[dict]) -> dict[str, str | None]:
    """Gemini API(Flash-Lite)로 오늘 기사와 기존 진행 중 이슈 간 의미 유사도 매칭을 수행한다.

    진행 중인 이슈가 없으면 Gemini 호출 없이 전부 매칭 없음으로 처리한다.
    호출 실패 시에도 안전하게 전부 매칭 없음(신규 이슈 생성)으로 대체한다.

    Args:
        articles: Step 4 요약 결과 기사 리스트
        active_issues: status="진행중"인 기존 이슈 리스트

    Returns:
        {article_id: issue_id 또는 None} dict
    """
    if not articles:
        return {}
    if not active_issues:
        return {a["id"]: None for a in articles}

    payload_articles = [
        {"id": a["id"], "title": a["title"], "companies": a.get("companies", [])} for a in articles
    ]
    payload_issues = [
        {"issue_id": i["issue_id"], "entity": i.get("entity", ""), "title": i.get("title", "")}
        for i in active_issues
    ]
    prompt = (
        "다음은 오늘 요약된 반도체 업계 뉴스 기사 목록과, 현재 진행 중인 이슈 목록이다. "
        "각 기사가 기존 이슈 중 같은 사건의 후속 보도이면 해당 issue_id를, "
        "새로운 사건이면 issue_id를 빈 문자열로 반환하라.\n\n"
        f"기사 목록: {json.dumps(payload_articles, ensure_ascii=False)}\n"
        f"진행 중 이슈 목록: {json.dumps(payload_issues, ensure_ascii=False)}"
    )
    try:
        result = gemini_client.call_gemini(prompt, _MATCH_SCHEMA, model=gemini_client.LITE_MODEL)
        matches = {m["article_id"]: (m.get("issue_id") or None) for m in result.get("matches", [])}
    except RuntimeError as exc:
        logger.error("이슈 매칭 실패, 전체 신규 이슈로 대체: %s", exc)
        matches = {}

    return {a["id"]: matches.get(a["id"]) for a in articles}


def generate_progress_summary(issue: dict, new_articles: list[dict]) -> str:
    """Gemini API로 이슈의 경과 요약 문단을 (재)생성한다.

    실패 시 기존 progress_summary를 그대로 유지한다.

    Args:
        issue: 갱신 대상 이슈 dict (기존 progress_summary 포함 가능)
        new_articles: 오늘 새로 연결된 기사 리스트

    Returns:
        경과 요약 문단 문자열
    """
    payload = [
        {"title": a.get("title", ""), "summary": (a.get("summary") or "")[:_SNIPPET_LEN]}
        for a in new_articles
    ]
    prompt = (
        f"'{issue.get('entity', '')}'의 '{issue.get('title', '')}' 이슈가 "
        f"{issue.get('first_seen', '')}부터 {issue.get('last_updated', '')}까지 이어지고 있다.\n"
        f"이전 경과 요약: {issue.get('progress_summary') or '(없음)'}\n"
        f"오늘 새로 추가된 기사: {json.dumps(payload, ensure_ascii=False)}\n"
        "지금까지의 경과를 한 문단으로 갱신 요약하라."
    )
    try:
        result = gemini_client.call_gemini(prompt, _PROGRESS_SCHEMA, model=_PROGRESS_SUMMARY_MODEL)
        return result["progress_summary"]
    except RuntimeError as exc:
        logger.error("경과 요약 생성 실패, 기존 요약 유지: %s", exc)
        return issue.get("progress_summary") or ""


def run(
    summarized_articles: list[dict],
    aliases_config: dict,
    issues_path: str,
    today: str,
) -> list[dict]:
    """Step 4.5 진입점.

    Args:
        summarized_articles: Step 4 결과 기사 리스트 ("핵심" tier, 요약 포함)
        aliases_config: config/company_aliases.yaml 로드 결과
        issues_path: data/state/issues.json 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        갱신된 status="진행중" 이슈 리스트 (Step 5에 전달)
    """
    issues = issue_tracking.load_issues(issues_path)
    active_issues = [i for i in issues if i.get("status") == "진행중"]

    matches = match_articles_to_issues(summarized_articles, active_issues)

    updated_articles_by_issue: dict[str, list[dict]] = {}
    for article in summarized_articles:
        issue_id = matches.get(article["id"])
        issue = issue_tracking.find_issue(issues, issue_id) if issue_id else None
        if issue is None:
            issue = create_issue(article, today, aliases_config)
            issues.append(issue)
        else:
            apply_match(issue, article, today)
        updated_articles_by_issue.setdefault(issue["issue_id"], []).append(article)

    for issue in issues:
        new_articles = updated_articles_by_issue.get(issue["issue_id"])
        if not new_articles:
            continue
        if needs_progress_summary(issue, today):
            issue["progress_summary"] = generate_progress_summary(issue, new_articles)

    close_stale_issues(issues, today)
    issue_tracking.save_issues(issues_path, issues)

    return [i for i in issues if i.get("status") == "진행중"]
