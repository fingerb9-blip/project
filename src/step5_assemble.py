"""Step 5. 조립 — 브리핑 마크다운 문서 및 대시보드 HTML 생성."""

import html
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from datetime import datetime as _datetime
from pathlib import Path
from urllib.parse import urlparse

from src import issue_tracking, run_status

_ALLOWED_URL_SCHEMES = {"http", "https"}
_CATEGORY_ORDER = ["메모리", "파운드리", "장비·소재", "팹리스·설계", "규제·정책"]
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


def _format_updated_label(target_date: str) -> str:
    """대시보드 헤더 부제목용 'YYYY년 M월 D일 · HH:MM 갱신' 문자열을 만든다.

    날짜는 target_date(파이프라인이 기준으로 삼은 날짜)를, 시각은 이 함수가 호출된
    실제 조립 시각(now)을 사용한다 — 두 값은 정상 실행에서는 같은 날이지만,
    권위 있는 값을 각각의 소스(파일명 vs 실행 시각)에서 가져오기 위해 분리했다.
    """
    d = _date.fromisoformat(target_date)
    now = _datetime.now()
    return f"{d.year}년 {d.month}월 {d.day}일 · {now.strftime('%H:%M')} 갱신"


def _list_dashboard_dates(dashboard_dir: Path, include: str | None = None) -> list[str]:
    """dashboard_dir에 이미 존재하는 날짜별 html 목록을 최신순으로 반환한다.

    Args:
        dashboard_dir: data/dashboard 디렉토리 경로
        include: 아직 파일로 쓰이지 않았더라도 목록에 포함할 날짜 (오늘 페이지 생성 시 사용)
    """
    dates = {p.stem for p in dashboard_dir.glob("*.html") if p.stem != "index"}
    if include:
        dates.add(include)
    return sorted(dates, reverse=True)


def _build_date_select(all_dates: list[str], target_date: str) -> str:
    """다른 날짜 브리핑으로 바로 이동할 수 있는 드롭다운을 만든다.

    "(오늘)" 라벨은 정적 HTML에 고정하면 나중에 열람할 때 날짜가 틀어지므로
    붙이지 않고, 클라이언트 스크립트(_DASHBOARD_SCRIPT)가 실제 접속 시각 기준으로 표시한다.
    """
    options = []
    for d in all_dates:
        selected = " selected" if d == target_date else ""
        options.append(f'<option value="{_esc(d)}"{selected}>{_esc(d)}</option>')
    return (
        '<select class="date-select" aria-label="날짜 선택" '
        "onchange=\"if (this.value) location.href = this.value + '.html'\">"
        + "".join(options)
        + "</select>"
    )


def _ordered_categories(articles: list[dict]) -> list[str]:
    """카테고리 필터 탭에 쓸 카테고리 목록을 config/categories.yaml 순서대로 정렬한다."""
    present: list[str] = []
    for article in articles:
        for category in article.get("category") or []:
            if category not in present:
                present.append(category)
    ordered = [c for c in _CATEGORY_ORDER if c in present]
    ordered += [c for c in present if c not in _CATEGORY_ORDER]
    return ordered


_DASHBOARD_SCRIPT = """\
<script>
(function () {
  var todayStr = new Date().toISOString().slice(0, 10);
  var dateSelect = document.querySelector('.date-select');
  if (dateSelect) {
    Array.prototype.forEach.call(dateSelect.options, function (opt) {
      if (opt.value === todayStr) { opt.textContent = opt.value + ' (오늘)'; }
    });
  }
  var tabs = document.querySelectorAll('.cat-tab');
  var cards = document.querySelectorAll('.card[data-categories]');
  tabs.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var category = btn.dataset.category;
      var wasActive = btn.classList.contains('active');
      tabs.forEach(function (b) { b.classList.remove('active'); });
      cards.forEach(function (card) { card.hidden = false; });
      if (!wasActive) {
        btn.classList.add('active');
        cards.forEach(function (card) {
          var cats = card.dataset.categories.split('|');
          card.hidden = cats.indexOf(category) === -1;
        });
      }
    });
  });
})();
</script>
"""


def build_dashboard_html(
    summarized_articles: list[dict],
    pending_review_articles: list[dict],
    collection_stats: dict,
    target_date: str,
    all_dates: list[str] | None = None,
    active_issues: list[dict] | None = None,
) -> str:
    """오늘의 핵심(카테고리 필터) -> 확인 필요(접이식) -> 수집 상태 -> 진행 중 이슈 순으로 카드형 대시보드 페이지를 만든다.

    Args:
        summarized_articles: Step 4 결과 기사 리스트 ("핵심" tier, 요약 포함)
        pending_review_articles: Step 3 결과 중 "확인 필요" tier 기사 리스트
        collection_stats: {source: {"today": int, "avg7d": float}} 형태의 소스별 수집 통계
        target_date: YYYY-MM-DD 형식 날짜 문자열
        all_dates: 날짜 선택 드롭다운에 표시할 전체 날짜 목록 (없으면 target_date만 표시)
        active_issues: data/state/issues.json 중 status="진행중"인 이슈 리스트 (Phase 3)

    Returns:
        단일 HTML 문서 문자열
    """
    all_dates = all_dates or [target_date]

    parts = [
        "<!doctype html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>반도체 뉴스 브리핑 {_esc(target_date)}</title>",
        '<link rel="stylesheet" href="style.css">',
        "</head><body>",
        '<div class="topbar">',
        '<div class="titleblock">',
        "<h1>반도체 뉴스 브리핑</h1>",
        f'<p class="subtitle">{_esc(_format_updated_label(target_date))}</p>',
        "</div>",
        _build_date_select(all_dates, target_date),
        "</div>",
        '<p class="backlink"><a href="index.html">&larr; 전체 목록</a></p>',
    ]

    parts.append('<section class="section-today">')
    parts.append('<h2 class="section-label">오늘의 핵심</h2>')

    categories = _ordered_categories(summarized_articles)
    if categories:
        parts.append('<div class="cat-tabs">')
        for category in categories:
            parts.append(
                f'<button type="button" class="cat-tab" data-category="{_esc(category)}">'
                f"{_esc(category)}</button>"
            )
        parts.append("</div>")

    if not summarized_articles:
        parts.append('<p class="empty">오늘 핵심 기사가 없습니다.</p>')

    parts.append('<div class="card-list">')
    for article in summarized_articles:
        article_categories = article.get("category") or ["미분류"]
        cats_attr = _esc("|".join(article_categories))
        safe_url = _safe_url(article["url"])
        title = _esc(article["title"])
        source = _esc(article["source"])
        link_open = f'<a href="{safe_url}">' if safe_url else ""
        link_close = "</a>" if safe_url else ""

        parts.append(f'<article class="card" data-categories="{cats_attr}">')
        parts.append('<div class="card-tags">')
        if article.get("summary_fallback"):
            parts.append('<span class="chip-muted">요약 없음</span>')
        else:
            tag = article.get("confirmation_tag") or ""
            if tag:
                tag_class = (
                    "tag-confirmed"
                    if "확정" in tag
                    else "tag-observed" if "관측" in tag else "tag-neutral"
                )
                parts.append(f'<span class="pill {tag_class}">{_esc(tag)}</span>')
        for category in article_categories:
            parts.append(f'<span class="pill pill-category">{_esc(category)}</span>')
        parts.append("</div>")
        parts.append(f'<h3 class="card-title">{link_open}{title}{link_close}</h3>')
        if article.get("summary_fallback"):
            meta = f"{source} · {link_open}원문 보기 ↗{link_close}" if safe_url else source
            parts.append(f'<p class="card-link-only">{meta}</p>')
        else:
            parts.append(f'<p class="card-summary">{_esc(article["summary"])}</p>')
            meta = f"{source} · {link_open}원문 보기 ↗{link_close}" if safe_url else source
            parts.append(f'<p class="card-meta">{meta}</p>')
        parts.append("</article>")
    parts.append("</div>")
    parts.append("</section>")

    parts.append('<section class="section-pending">')
    parts.append("<details class=\"pending-details\">")
    parts.append(
        f'<summary>확인 필요 <span class="count-badge">{len(pending_review_articles)}건</span></summary>'
    )
    if not pending_review_articles:
        parts.append('<p class="empty">없음</p>')
    else:
        parts.append('<ul class="pending-list">')
        for article in pending_review_articles:
            safe_url = _safe_url(article["url"])
            title = _esc(article["title"])
            link = f'<a href="{safe_url}">{title}</a>' if safe_url else title
            parts.append(f'<li>{link} <span class="meta">({_esc(article["source"])})</span></li>')
        parts.append("</ul>")
    parts.append("</details>")
    parts.append("</section>")

    parts.append('<section class="section-stats">')
    parts.append('<h2 class="section-label">수집 상태</h2>')
    parts.append('<div class="stat-chips">')
    for source, stats in collection_stats.items():
        today_count = stats.get("today", 0)
        avg7d = stats.get("avg7d", 0)
        css_class = "warn" if avg7d > 0 and today_count < avg7d * 0.3 else "chip"
        parts.append(
            f'<span class="{css_class}">{_esc(source)} <strong>{today_count}</strong> '
            f'<span class="chip-avg">(평균 {avg7d:.1f})</span></span>'
        )
    parts.append("</div>")
    parts.append("</section>")

    if active_issues:
        parts.append('<section class="section-issues">')
        parts.append('<h2 class="section-label">진행 중 이슈</h2>')
        parts.append('<div class="card-list">')
        for issue in active_issues:
            article_count = len(issue.get("related_article_ids") or [])
            parts.append('<article class="card">')
            parts.append(
                f"<p>[{_esc(issue.get('entity', ''))}] <strong>{_esc(issue.get('title', ''))}</strong></p>"
            )
            parts.append(
                f'<p class="card-meta">{_esc(issue.get("first_seen", ""))} ~ '
                f'{_esc(issue.get("last_updated", ""))} · 관련 기사 {article_count}건</p>'
            )
            if issue.get("progress_summary"):
                parts.append(f'<p class="card-summary">경과 요약: {_esc(issue["progress_summary"])}</p>')
            parts.append("</article>")
        parts.append("</div>")
        parts.append("</section>")

    parts.append(_DASHBOARD_SCRIPT)
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
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
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


def build_index_html(
    dashboard_dir: Path,
    state_path: Path,
    issues_path: Path | None = None,
    now: str | None = None,
) -> str:
    """data/dashboard/*.html 파일 목록으로 날짜별 인덱스 페이지를 만든다.

    run_status.json의 마지막 실행 상태를 상단 배지로 보여준다 ("침묵 실패 방지").
    issues_path가 주어지면 24시간 이내 확정된 속보를 상단 배너로 함께 보여준다 (Phase 3).

    Args:
        dashboard_dir: data/dashboard 디렉토리 경로 (날짜별 html이 이미 생성돼 있어야 함)
        state_path: data/state/run_status.json 경로
        issues_path: data/state/issues.json 경로 (속보 배너용, 선택)
        now: 현재 시각 ISO8601 문자열 (테스트용, 기본값은 UTC 현재 시각)

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
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>반도체 뉴스 브리핑</title>",
        '<link rel="stylesheet" href="style.css">',
        "</head><body>",
        '<div class="titleblock">',
        "<h1>반도체 뉴스 브리핑</h1>",
        badge,
        "</div>",
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

    if not dates:
        parts.append('<p class="empty">아직 생성된 브리핑이 없습니다.</p>')
    else:
        latest = dates[0]
        parts.append(f'<p><a class="latest" href="{latest}.html">최신 브리핑 보기 ({latest})</a></p>')
        parts.append('<h2 class="section-label">지난 브리핑</h2>')
        parts.append('<ul class="date-list">')
        for d in dates:
            parts.append(f'<li><a href="{d}.html">{d}</a></li>')
        parts.append("</ul>")

    parts.append("</body></html>")
    return "\n".join(parts)


_DASHBOARD_CSS = """\
:root {
  --bg: #fafafa;
  --surface: #ffffff;
  --border: #e4e4e4;
  --text: #1a1a1a;
  --text-muted: #6b6b6b;
  --accent: #2563eb;
  --accent-bg: #eff6ff;
  --confirmed-bg: #d4edda;
  --confirmed-text: #155724;
  --observed-bg: #fff3cd;
  --observed-text: #856404;
  --warn-bg: #f8d7da;
  --warn-text: #721c24;
  --chip-bg: #f1f3f5;
  --chip-text: #495057;
  --radius: 10px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #16181c;
    --surface: #202329;
    --border: #33373f;
    --text: #e8e9eb;
    --text-muted: #9a9ea6;
    --accent: #6ea8fe;
    --accent-bg: #1c2b47;
    --confirmed-bg: #15351f;
    --confirmed-text: #7fdb98;
    --observed-bg: #3a2f10;
    --observed-text: #f0c869;
    --warn-bg: #3d1c22;
    --warn-text: #f0a3ac;
    --chip-bg: #2a2d33;
    --chip-text: #c3c6cc;
  }
}

* { box-sizing: border-box; }

body {
  font-family: -apple-system, "Segoe UI", sans-serif;
  max-width: 860px; margin: 2rem auto; padding: 0 1rem 3rem;
  color: var(--text); background: var(--bg);
  font-variant-numeric: tabular-nums;
}

a { color: var(--accent); }

.titleblock h1, .topbar h1 { font-size: 1.5rem; margin: 0; text-wrap: balance; }

.topbar {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 1rem; flex-wrap: wrap;
}
.subtitle { margin: 0.25rem 0 0; color: var(--text-muted); font-size: 0.85rem; }
.date-select {
  border: 1px solid var(--border); border-radius: 8px; padding: 0.5rem 0.8rem;
  background: var(--surface); color: var(--text); font-size: 0.9rem;
}

.backlink { margin: 0.6rem 0 1.6rem; font-size: 0.85rem; }
.backlink a { color: var(--text-muted); text-decoration: none; }
.backlink a:hover { text-decoration: underline; }

.section-label {
  font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--text-muted); font-weight: 600; margin: 2.2rem 0 0.9rem; border: none; padding: 0;
}
.section-today .section-label { margin-top: 0; }

.cat-tabs { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.2rem; }
.cat-tab {
  border: 1px solid var(--border); background: var(--surface); color: var(--text);
  border-radius: 999px; padding: 0.4rem 0.9rem; font-size: 0.85rem; cursor: pointer;
}
.cat-tab:hover { border-color: var(--accent); }
.cat-tab.active { background: var(--accent-bg); border-color: var(--accent); color: var(--accent); font-weight: 600; }

.card-list { display: flex; flex-direction: column; gap: 0.9rem; }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 1rem 1.1rem;
}
.card-tags { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.55rem; }
.pill, .chip-muted {
  display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px;
  font-size: 0.78rem; font-weight: 600;
}
.chip-muted { color: var(--text-muted); background: var(--chip-bg); font-weight: 500; }
.tag-confirmed { background: var(--confirmed-bg); color: var(--confirmed-text); }
.tag-observed { background: var(--observed-bg); color: var(--observed-text); }
.tag-neutral { background: var(--chip-bg); color: var(--chip-text); }
.pill-category { background: var(--chip-bg); color: var(--chip-text); font-weight: 500; }

.card-title { font-size: 1.05rem; margin: 0 0 0.35rem; text-wrap: balance; }
.card-title a { color: var(--text); text-decoration: none; }
.card-title a:hover { text-decoration: underline; }
.card-summary { margin: 0 0 0.4rem; color: var(--text-muted); font-size: 0.92rem; line-height: 1.5; }
.card-meta, .card-link-only { margin: 0; color: var(--text-muted); font-size: 0.82rem; }

.pending-details {
  border: 1px solid var(--border); border-radius: var(--radius); padding: 0.8rem 1rem; background: var(--surface);
}
.pending-details summary {
  cursor: pointer; font-weight: 600; list-style: none; display: flex; align-items: center; gap: 0.5rem;
}
.pending-details summary::-webkit-details-marker { display: none; }
.pending-details summary::after { content: "\\25BE"; margin-left: auto; color: var(--text-muted); }
.pending-details[open] summary::after { content: "\\25B4"; }
.count-badge { background: var(--chip-bg); color: var(--chip-text); border-radius: 999px; padding: 0.1rem 0.55rem; font-size: 0.78rem; }
.pending-list { margin: 0.8rem 0 0; padding-left: 1.1rem; }
.pending-list li { margin-bottom: 0.4rem; font-size: 0.92rem; }

.section-stats { overflow-x: auto; }
.stat-chips { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.chip, .warn {
  display: inline-flex; align-items: center; gap: 0.35rem;
  border-radius: 999px; padding: 0.35rem 0.8rem; font-size: 0.85rem; white-space: nowrap;
}
.chip { background: var(--chip-bg); color: var(--chip-text); }
.warn { background: var(--warn-bg); color: var(--warn-text); font-weight: 600; }
.chip-avg { opacity: 0.75; font-size: 0.9em; }

.empty { color: var(--text-muted); font-size: 0.9rem; }

.badge { display: inline-block; padding: 0.3rem 0.7rem; border-radius: 6px; font-size: 0.9rem; margin-top: 0.6rem; }
.badge.ok { background: var(--confirmed-bg); color: var(--confirmed-text); }
.badge.fail { background: var(--warn-bg); color: var(--warn-text); }
.badge.unknown { background: var(--chip-bg); color: var(--chip-text); }
a.latest { font-weight: bold; font-size: 1.1rem; }
.date-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.4rem; }
.date-list a { text-decoration: none; }
.date-list a:hover { text-decoration: underline; }
.alert-banner { background: var(--warn-bg); color: var(--warn-text); border: 1px solid var(--warn-text); border-radius: var(--radius); padding: 0.6rem 1rem; margin: 0.8rem 0; }
.alert-banner p { margin: 0.2rem 0; font-weight: bold; }
.alert-banner a { color: inherit; }

@media (max-width: 480px) {
  body { margin: 1rem auto; padding: 0 0.7rem 2rem; font-size: 0.95rem; }
  .titleblock h1, .topbar h1 { font-size: 1.2rem; }
  .topbar { flex-direction: column; align-items: stretch; }
  .date-select { width: 100%; }
  .section-label { margin: 1.6rem 0 0.7rem; }
  .card { padding: 0.75rem 0.85rem; }
  .card-title { font-size: 0.98rem; }
  .pending-details { padding: 0.65rem 0.8rem; }
  .stat-chips { gap: 0.4rem; }
  .chip, .warn { padding: 0.3rem 0.65rem; font-size: 0.8rem; }
}
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

    all_dates = _list_dashboard_dates(dashboard_dir, include=today)
    dashboard_html = build_dashboard_html(
        summarized_articles,
        pending_review_articles,
        collection_stats,
        today,
        all_dates,
        active_issues,
    )
    (dashboard_dir / f"{today}.html").write_text(dashboard_html, encoding="utf-8")

    (dashboard_dir / "style.css").write_text(_DASHBOARD_CSS, encoding="utf-8")

    index_html = build_index_html(
        dashboard_dir, Path(state_path), issues_path=Path(issues_path) if issues_path else None
    )
    (dashboard_dir / "index.html").write_text(index_html, encoding="utf-8")

    return briefing
