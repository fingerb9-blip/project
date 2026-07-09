"""Step 5. 조립 — 브리핑 마크다운 문서 및 대시보드 HTML 생성."""

import html
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse

import yaml

from src import issue_tracking, run_status

_ALLOWED_URL_SCHEMES = {"http", "https"}
_ALERT_SUPPRESS_WINDOW_HOURS = 24


def build_briefing(
    summarized_articles: list[dict],
    pending_review_articles: list[dict],
    collection_stats: dict,
    active_issues: list[dict] | None = None,
) -> str:
    """오늘의 핵심 -> 카테고리별 -> 확인 필요 목록 -> 수집 상태 -> 진행 중 이슈 순으로 브리핑 문서를 조립한다.

    Args:
        summarized_articles: Step 4 결과 기사 리스트 ("핵심" tier, 요약 포함)
        pending_review_articles: Step 3 결과 중 "확인 필요" tier 기사 리스트
        collection_stats: {source: {"today": int, "avg7d": float}} 형태의 소스별 수집 통계
        active_issues: data/state/issues.json 중 status="진행중"인 이슈 리스트 (Phase 3)

    Returns:
        마크다운 형식의 브리핑 문서 문자열
    """
    lines = ["# 반도체 뉴스 데일리 브리핑", ""]

    lines.append("## 오늘의 핵심")
    if not summarized_articles:
        lines.append("- 오늘 핵심 기사가 없습니다.")
    for article in summarized_articles:
        if article.get("summary_fallback"):
            lines.append(f"- [{article['title']}]({article['url']}) ({article['source']})")
        else:
            tag = article.get("confirmation_tag", "")
            lines.append(f"- {tag} **{article['title']}**")
            lines.append(f"  {article['summary']}")
            lines.append(f"  ({article['source']}, {article['url']})")
    lines.append("")

    lines.append("## 카테고리별")
    by_category: dict[str, list[dict]] = {}
    for article in summarized_articles:
        for category in article.get("category") or ["미분류"]:
            by_category.setdefault(category, []).append(article)
    if not by_category:
        lines.append("- 해당 없음")
    for category, articles in by_category.items():
        lines.append(f"### {category}")
        for article in articles:
            lines.append(f"- {article['title']} ({article['source']})")
    lines.append("")

    lines.append("## 확인 필요")
    if not pending_review_articles:
        lines.append("- 없음")
    for article in pending_review_articles:
        lines.append(f"- [{article['title']}]({article['url']}) ({article['source']})")
    lines.append("")

    lines.append("## 수집 상태")
    lines.append("| 소스 | 오늘 건수 | 최근 7일 평균 |")
    lines.append("|---|---|---|")
    for source, stats in collection_stats.items():
        lines.append(f"| {source} | {stats.get('today', 0)} | {stats.get('avg7d', 0):.1f} |")
    lines.append("")

    if active_issues:
        lines.append("## 진행 중 이슈")
        for issue in active_issues:
            article_count = len(issue.get("related_article_ids") or [])
            lines.append(
                f"- [{issue.get('entity', '')}] {issue.get('title', '')} "
                f"({issue.get('first_seen', '')} ~ {issue.get('last_updated', '')}, "
                f"관련 기사 {article_count}건)"
            )
            if issue.get("progress_summary"):
                lines.append(f"  경과 요약: {issue['progress_summary']}")

    return "\n".join(lines) + "\n"


def _esc(text) -> str:
    """HTML 삽입 전 이스케이프 처리. RSS/뉴스 소스에서 온 텍스트는 신뢰할 수 없다."""
    return html.escape(str(text), quote=True)


def _safe_url(url: str) -> str | None:
    """http/https 스킴만 허용해 javascript: 등 위험한 URL을 걸러낸다."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        return None
    return html.escape(url, quote=True)


def _noise_report_issue_url(article: dict, repo_url: str | None) -> str | None:
    """'노이즈로 표시' 버튼이 열 GitHub 새 이슈 URL을 만든다. repo_url이 없으면 None."""
    if not repo_url:
        return None
    body = (
        f"article_id: {article['id']}\n"
        f"url: {article['url']}\n"
        f"title: {article['title']}\n"
        "reason: noise\n"
    )
    query = urlencode(
        {"title": f"[노이즈 신고] {article['title']}", "body": body, "labels": "noise-report"}
    )
    return f"{repo_url}/issues/new?{query}"


def build_dashboard_html(
    summarized_articles: list[dict],
    pending_review_articles: list[dict],
    collection_stats: dict,
    target_date: str,
    active_issues: list[dict] | None = None,
    repo_url: str | None = None,
) -> str:
    """오늘의 핵심 -> 카테고리별 -> 확인 필요 -> 수집 상태 -> 진행 중 이슈 순으로 카드형 HTML 대시보드 페이지를 만든다.

    Args:
        summarized_articles: Step 4 결과 기사 리스트 ("핵심" tier, 요약 포함)
        pending_review_articles: Step 3 결과 중 "확인 필요" tier 기사 리스트
        collection_stats: {source: {"today": int, "avg7d": float}} 형태의 소스별 수집 통계
        target_date: YYYY-MM-DD 형식 날짜 문자열
        active_issues: data/state/issues.json 중 status="진행중"인 이슈 리스트 (Phase 3)
        repo_url: GitHub 리포지토리 URL (노이즈 신고 버튼용, 선택)

    Returns:
        단일 HTML 문서 문자열
    """
    parts = [
        "<!doctype html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        f"<title>반도체 뉴스 브리핑 {_esc(target_date)}</title>",
        '<link rel="stylesheet" href="style.css">',
        "</head><body>",
        '<p><a href="index.html">&larr; 전체 목록</a></p>',
        f"<h1>반도체 뉴스 데일리 브리핑 — {_esc(target_date)}</h1>",
    ]

    parts.append('<section id="today-core"><h2>오늘의 핵심</h2>')
    parts.append(
        '<label class="filter-toggle"><input type="checkbox" id="deep-tech-filter"> '
        "학회·특허만 보기</label>"
    )
    if not summarized_articles:
        parts.append("<p>오늘 핵심 기사가 없습니다.</p>")
    for article in summarized_articles:
        safe_url = _safe_url(article["url"])
        title = _esc(article["title"])
        source = _esc(article["source"])
        source_type = _esc(article.get("source_type", "언론"))
        link = f'<a href="{safe_url}">{title}</a>' if safe_url else title
        parts.append(f'<article class="card" data-source-type="{source_type}">')
        if article.get("summary_fallback"):
            parts.append(f'<p>{link} ({source} · <span class="badge-type">{source_type}</span>)</p>')
        else:
            tag = _esc(article.get("confirmation_tag", ""))
            parts.append(f"<p>{tag} <strong>{title}</strong></p>")
            parts.append(f"<p>{_esc(article['summary'])}</p>")
            parts.append(
                f'<p class="meta">{source} · <span class="badge-type">{source_type}</span> · {link}</p>'
            )
        issue_url = _noise_report_issue_url(article, repo_url)
        if issue_url:
            safe_issue_url = html.escape(issue_url, quote=True)
            parts.append(
                f'<p class="meta"><a class="noise-btn" href="{safe_issue_url}" '
                'target="_blank" rel="noopener" '
                "onclick=\"this.nextElementSibling.hidden=false\">노이즈로 표시</a> "
                '<span class="toast" hidden>이 기사를 제외 대상으로 표시했습니다</span></p>'
            )
        parts.append("</article>")
    parts.append("</section>")

    parts.append("<section><h2>카테고리별</h2>")
    by_category: dict[str, list[dict]] = {}
    for article in summarized_articles:
        for category in article.get("category") or ["미분류"]:
            by_category.setdefault(category, []).append(article)
    if not by_category:
        parts.append("<p>해당 없음</p>")
    for category, articles in by_category.items():
        parts.append(f"<h3>{_esc(category)}</h3><ul>")
        for article in articles:
            parts.append(f"<li>{_esc(article['title'])} ({_esc(article['source'])})</li>")
        parts.append("</ul>")
    parts.append("</section>")

    parts.append("<section><h2>확인 필요</h2>")
    if not pending_review_articles:
        parts.append("<p>없음</p>")
    else:
        parts.append("<ul>")
        for article in pending_review_articles:
            safe_url = _safe_url(article["url"])
            title = _esc(article["title"])
            link = f'<a href="{safe_url}">{title}</a>' if safe_url else title
            parts.append(f"<li>{link} ({_esc(article['source'])})</li>")
        parts.append("</ul>")
    parts.append("</section>")

    parts.append(
        "<section><h2>수집 상태</h2>"
        "<table><tr><th>소스</th><th>오늘 건수</th><th>최근 7일 평균</th></tr>"
    )
    for source, stats in collection_stats.items():
        today_count = stats.get("today", 0)
        avg7d = stats.get("avg7d", 0)
        warn = ' class="warn"' if avg7d > 0 and today_count < avg7d * 0.3 else ""
        parts.append(
            f"<tr{warn}><td>{_esc(source)}</td><td>{today_count}</td><td>{avg7d:.1f}</td></tr>"
        )
    parts.append("</table></section>")

    if active_issues:
        parts.append("<section><h2>진행 중 이슈</h2>")
        for issue in active_issues:
            article_count = len(issue.get("related_article_ids") or [])
            parts.append('<article class="card">')
            parts.append(
                f"<p>[{_esc(issue.get('entity', ''))}] <strong>{_esc(issue.get('title', ''))}</strong></p>"
            )
            parts.append(
                f'<p class="meta">{_esc(issue.get("first_seen", ""))} ~ '
                f'{_esc(issue.get("last_updated", ""))} · 관련 기사 {article_count}건</p>'
            )
            if issue.get("progress_summary"):
                parts.append(f"<p>경과 요약: {_esc(issue['progress_summary'])}</p>")
            parts.append("</article>")
        parts.append("</section>")

    parts.append(
        "<script>"
        "(function(){"
        "var cb=document.getElementById('deep-tech-filter');"
        "if(!cb)return;"
        "cb.addEventListener('change',function(){"
        "var only=cb.checked;"
        "document.querySelectorAll('#today-core .card').forEach(function(card){"
        "var t=card.dataset.sourceType;"
        "var deep=(t==='학회'||t==='특허');"
        "card.style.display=(only&&!deep)?'none':'';"
        "});"
        "});"
        "})();"
        "</script>"
    )
    parts.append("</body></html>")
    return "\n".join(parts)


def build_alert_banner_html(alerts: list[dict]) -> str:
    """이상 신호 감지(Phase 3)가 확정한 속보를 index.html 상단 배너로 렌더링한다.

    이메일이 아니라 대시보드 즉시 갱신·재배포로 속보를 전달하는 채널이다.

    Args:
        alerts: {issue_id, entity, headline, tag} 형태의 확정 속보 리스트

    Returns:
        배너 HTML 조각 (alerts가 비어 있으면 빈 문자열)
    """
    if not alerts:
        return ""
    parts = ['<div class="alert-banner">']
    for alert in alerts:
        tag = _esc(alert.get("tag", ""))
        entity = _esc(alert.get("entity", ""))
        headline = _esc(alert.get("headline", ""))
        issue_id = alert.get("issue_id", "")
        parts.append(
            f'<p>🚨 {tag} [{entity}] {headline} '
            f'<a href="alerts/{_esc(issue_id)}.html">상세 보기</a></p>'
        )
    parts.append("</div>")
    return "".join(parts)


def build_alert_detail_html(issue: dict) -> str:
    """속보 확정 이슈의 상세 페이지(data/dashboard/alerts/<issue_id>.html)를 만든다.

    Args:
        issue: issues.json의 이슈 항목 (entity, title/headline, tag, related_article_ids 등)

    Returns:
        단일 HTML 문서 문자열
    """
    title = issue.get("headline") or issue.get("title", "")
    parts = [
        "<!doctype html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        f"<title>속보 — {_esc(title)}</title>",
        '<link rel="stylesheet" href="../style.css">',
        "</head><body>",
        '<p><a href="../index.html">&larr; 전체 목록</a></p>',
        f"<h1>🚨 {_esc(issue.get('tag', ''))} [{_esc(issue.get('entity', ''))}] {_esc(title)}</h1>",
        f'<p class="meta">최초 감지: {_esc(issue.get("first_seen", ""))} · '
        f'최근 갱신: {_esc(issue.get("last_updated", ""))}</p>',
    ]
    if issue.get("progress_summary"):
        parts.append(f"<p>{_esc(issue['progress_summary'])}</p>")
    parts.append("</body></html>")
    return "\n".join(parts)


def load_pending_keywords(pending_path: Path) -> list[dict]:
    """config/keywords_pending.yaml의 candidates를 로드한다 (없으면 빈 리스트).

    daily_briefing(main.py)과 hourly_anomaly_check(step1_5_anomaly_detect.py) 양쪽에서
    index.html을 재생성할 때 공통으로 써야 관리자 후보 섹션이 사라지지 않는다.

    Args:
        pending_path: config/keywords_pending.yaml 경로

    Returns:
        candidates 리스트 (파일이 없으면 빈 리스트)
    """
    pending_path = Path(pending_path)
    if not pending_path.exists():
        return []
    with pending_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("candidates", [])


def build_pending_keywords_section_html(candidates: list[dict]) -> str:
    """config/keywords_pending.yaml 후보 목록을 index.html 관리자 섹션으로 렌더링한다.

    Args:
        candidates: keywords_pending.yaml의 candidates 리스트

    Returns:
        섹션 HTML 조각 (candidates가 비어 있으면 빈 문자열)
    """
    if not candidates:
        return ""
    parts = [
        "<section><h2>피드백 키워드 후보 (승인 대기)</h2><table>",
        "<tr><th>키워드</th><th>신고 횟수</th><th>최근 신고</th></tr>",
    ]
    for candidate in sorted(candidates, key=lambda c: c.get("report_count", 0), reverse=True):
        warn = ' class="warn"' if candidate.get("priority") else ""
        parts.append(
            f"<tr{warn}><td>{_esc(candidate.get('keyword', ''))}</td>"
            f"<td>{_esc(candidate.get('report_count', 0))}</td>"
            f"<td>{_esc(candidate.get('last_flagged_at', ''))}</td></tr>"
        )
    parts.append("</table></section>")
    return "".join(parts)


def build_index_html(
    dashboard_dir: Path,
    state_path: Path,
    issues_path: Path | None = None,
    now: str | None = None,
    pending_keywords: list[dict] | None = None,
) -> str:
    """data/dashboard/*.html 파일 목록으로 날짜별 인덱스 페이지를 만든다.

    run_status.json의 마지막 실행 상태를 상단 배지로 보여준다 ("침묵 실패 방지").
    issues_path가 주어지면 24시간 이내 확정된 속보를 상단 배너로 함께 보여준다 (Phase 3).
    pending_keywords가 주어지면 관리자용 키워드 후보 섹션을 함께 보여준다.

    Args:
        dashboard_dir: data/dashboard 디렉토리 경로 (날짜별 html이 이미 생성돼 있어야 함)
        state_path: data/state/run_status.json 경로
        issues_path: data/state/issues.json 경로 (속보 배너용, 선택)
        now: 현재 시각 ISO8601 문자열 (테스트용, 기본값은 UTC 현재 시각)
        pending_keywords: config/keywords_pending.yaml의 candidates 리스트 (관리자 섹션용, 선택)

    Returns:
        단일 HTML 문서 문자열
    """
    dates = sorted(
        (p.stem for p in dashboard_dir.glob("*.html") if p.stem != "index"),
        reverse=True,
    )

    status = run_status.load_status(state_path)
    if status is None:
        badge = '<p class="badge unknown">실행 이력 없음</p>'
    elif status.get("last_run_status") == "success":
        badge = (
            f'<p class="badge ok">최근 실행 성공 '
            f'(마지막 성공: {_esc(status.get("last_success_at", "-"))})</p>'
        )
    else:
        badge = (
            f'<p class="badge fail">최근 실행 실패 '
            f'(마지막 성공: {_esc(status.get("last_success_at", "-"))})</p>'
        )

    parts = [
        "<!doctype html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        "<title>반도체 뉴스 브리핑</title>",
        '<link rel="stylesheet" href="style.css">',
        "</head><body>",
        "<h1>반도체 뉴스 데일리 브리핑</h1>",
        badge,
    ]

    if issues_path is not None:
        now_dt = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        issues = issue_tracking.load_issues(issues_path)
        recent_alerts = []
        for issue in issues:
            if issue.get("status") != "진행중" or not issue.get("last_alerted_at"):
                continue
            alerted_at = datetime.fromisoformat(issue["last_alerted_at"])
            if now_dt - alerted_at < timedelta(hours=_ALERT_SUPPRESS_WINDOW_HOURS):
                recent_alerts.append(issue)
        banner = build_alert_banner_html(recent_alerts)
        if banner:
            parts.append(banner)

    if pending_keywords:
        parts.append(build_pending_keywords_section_html(pending_keywords))

    if not dates:
        parts.append("<p>아직 생성된 브리핑이 없습니다.</p>")
    else:
        latest = dates[0]
        parts.append(f'<p><a class="latest" href="{latest}.html">최신 브리핑 보기 ({latest})</a></p>')
        parts.append("<h2>지난 브리핑</h2><ul>")
        for d in dates:
            parts.append(f'<li><a href="{d}.html">{d}</a></li>')
        parts.append("</ul>")

    parts.append("</body></html>")
    return "\n".join(parts)


_DASHBOARD_CSS = """\
body { font-family: -apple-system, "Segoe UI", sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fafafa; }
h1 { font-size: 1.5rem; }
h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 2px solid #ddd; padding-bottom: 0.3rem; }
.card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 0.8rem 1rem; margin-bottom: 0.8rem; }
.meta { color: #666; font-size: 0.85rem; }
.badge-type { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 4px; background: #e2e3e5; font-size: 0.78rem; }
.filter-toggle { display: inline-block; margin-bottom: 0.6rem; font-size: 0.9rem; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: left; }
tr.warn td { background: #fff3cd; }
.badge { display: inline-block; padding: 0.3rem 0.7rem; border-radius: 6px; font-size: 0.9rem; }
.badge.ok { background: #d4edda; color: #155724; }
.badge.fail { background: #f8d7da; color: #721c24; }
.badge.unknown { background: #e2e3e5; color: #383d41; }
a.latest { font-weight: bold; font-size: 1.1rem; }
.alert-banner { background: #f8d7da; border: 1px solid #f1aeb5; border-radius: 8px; padding: 0.6rem 1rem; margin: 0.8rem 0; }
.alert-banner p { margin: 0.2rem 0; font-weight: bold; }
.noise-btn { font-size: 0.8rem; color: #a94442; text-decoration: none; border: 1px solid #a94442; border-radius: 4px; padding: 0.1rem 0.4rem; }
.toast { font-size: 0.8rem; color: #155724; margin-left: 0.4rem; }
"""


def run(
    summarized_articles: list[dict],
    pending_review_articles: list[dict],
    collection_stats: dict,
    archive_path: str,
    dashboard_dir: str,
    today: str,
    state_path: str,
    issues_path: str | None = None,
    repo_url: str | None = None,
) -> str:
    """Step 5 진입점. 마크다운 아카이브와 HTML 대시보드를 함께 생성한다.

    Args:
        summarized_articles: data/summarized/YYYY-MM-DD.json 로드 결과
        pending_review_articles: data/classified/YYYY-MM-DD.json 중 "확인 필요" tier 기사
        collection_stats: 소스별 수집 통계
        archive_path: data/archive/YYYY-MM-DD.md 저장 경로
        dashboard_dir: data/dashboard 디렉토리 경로
        today: YYYY-MM-DD 형식 날짜 문자열
        state_path: data/state/run_status.json 경로 (index.html 상태 배지용)
        issues_path: data/state/issues.json 경로 (진행 중 이슈 타임라인·속보 배너용, Phase 3, 선택)
        repo_url: GitHub 리포지토리 URL (노이즈 신고 버튼용, 선택)

    Returns:
        생성된 브리핑 마크다운 문서 문자열 (archive_path에도 저장)
    """
    active_issues = []
    if issues_path is not None:
        active_issues = [
            issue
            for issue in issue_tracking.load_issues(Path(issues_path))
            if issue.get("status") == "진행중"
        ]

    briefing = build_briefing(
        summarized_articles, pending_review_articles, collection_stats, active_issues
    )

    archive_path = Path(archive_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(briefing, encoding="utf-8")

    dashboard_dir = Path(dashboard_dir)
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    dashboard_html = build_dashboard_html(
        summarized_articles, pending_review_articles, collection_stats, today, active_issues, repo_url
    )
    (dashboard_dir / f"{today}.html").write_text(dashboard_html, encoding="utf-8")

    (dashboard_dir / "style.css").write_text(_DASHBOARD_CSS, encoding="utf-8")

    index_html = build_index_html(
        dashboard_dir, Path(state_path), issues_path=Path(issues_path) if issues_path else None
    )
    (dashboard_dir / "index.html").write_text(index_html, encoding="utf-8")

    return briefing
