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
from src.step2_dedup import _token_jaccard

logger = logging.getLogger(__name__)

_PROGRESS_SUMMARY_MIN_DAYS = 3
_CLOSE_AFTER_DAYS = 7
_SNIPPET_LEN = 300
# 같은 사건이 여러 이슈로 쪼개졌을 때 병합 판정 임계값(제목 토큰 자카드). step2 근접중복
# 임계값과 동일하게 두어 "동일 사건" 기준을 일관되게 맞춘다.
_ISSUE_MERGE_JACCARD = 0.3
# 무료 티어 할당량이 넉넉하지 않아 LITE_MODEL로 전환했다. 품질이 부족하면
# 이 한 줄만 DEFAULT_MODEL로 되돌리면 된다.
_PROGRESS_SUMMARY_MODEL = gemini_client.LITE_MODEL

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


def consolidate_issues(issues: list[dict], today: str) -> list[dict]:
    """같은 사건이 여러 진행 중 이슈로 쪼개진 것을 하나로 병합한다.

    Gemini 매칭이 실패(무료 티어 503/429)하면 오늘 기사가 전부 개별 신규 이슈로 만들어져
    같은 사건(예: 'SK하이닉스 나스닥 ADR 상장')이 수십 개 이슈로 파편화된다. 진행 중 이슈
    중 같은 entity이고 제목 토큰 유사도가 임계 이상인 것끼리 union-find로 묶어, 관련 기사
    ID를 합치고 first_seen은 가장 이르게·last_updated는 가장 늦게 보존한다.

    entity가 '미상'인 이슈는 오병합 위험이 커 병합 대상에서 제외한다. 종료 이슈는 건드리지
    않는다.

    Args:
        issues: 전체 이슈 리스트 (진행중 + 종료)
        today: YYYY-MM-DD (시그니처 일관성용, 현재 로직에선 미사용)

    Returns:
        병합이 적용된 이슈 리스트 (종료 이슈는 원래대로 유지)
    """
    del today  # 병합 판정에 현재 날짜는 쓰지 않는다(시그니처 일관성용).
    active = [i for i in issues if i.get("status") == "진행중"]
    closed = [i for i in issues if i.get("status") != "진행중"]

    parent = list(range(len(active)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)  # 더 앞선(=먼저 등장한) 이슈를 대표로 둔다

    for a in range(len(active)):
        for b in range(a + 1, len(active)):
            entity = active[a].get("entity", "")
            if entity == "미상" or entity != active[b].get("entity", ""):
                continue
            if _token_jaccard(active[a].get("title", ""), active[b].get("title", "")) >= _ISSUE_MERGE_JACCARD:
                union(a, b)

    groups: dict[int, list[int]] = {}
    for idx in range(len(active)):
        groups.setdefault(find(idx), []).append(idx)

    merged: list[dict] = []
    for root, members in groups.items():
        if len(members) == 1:
            merged.append(active[members[0]])
            continue
        # 대표 이슈: 관련 기사 많은 것 우선, 동률이면 first_seen 이른 것
        members_sorted = sorted(
            members,
            key=lambda m: (-len(active[m].get("related_article_ids") or []), active[m].get("first_seen", "")),
        )
        base = active[members_sorted[0]]
        all_ids: list[str] = []
        for m in members:
            all_ids.extend(active[m].get("related_article_ids") or [])
        base["related_article_ids"] = list(dict.fromkeys(all_ids))
        base["first_seen"] = min(active[m].get("first_seen", "") for m in members)
        base["last_updated"] = max(active[m].get("last_updated", "") for m in members)
        merged.append(base)

    return closed + merged


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

    # 같은 사건이 여러 신규 이슈로 쪼개진 것을 병합한다(Gemini 매칭 실패 시 파편화 방지).
    issues = consolidate_issues(issues, today)

    for issue in issues:
        new_articles = updated_articles_by_issue.get(issue["issue_id"])
        if not new_articles:
            continue
        if needs_progress_summary(issue, today):
            issue["progress_summary"] = generate_progress_summary(issue, new_articles)

    close_stale_issues(issues, today)
    issue_tracking.save_issues(issues_path, issues)

    return [i for i in issues if i.get("status") == "진행중"]
