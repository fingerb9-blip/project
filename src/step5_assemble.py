"""Step 5. 조립 — 브리핑 마크다운 문서 및 대시보드 HTML 생성."""

import html
from pathlib import Path
from urllib.parse import urlparse

from src import run_status

_ALLOWED_URL_SCHEMES = {"http", "https"}


def build_briefing(
    summarized_articles: list[dict],
    pending_review_articles: list[dict],
    collection_stats: dict,
) -> str:
    """오늘의 핵심 -> 카테고리별 -> 확인 필요 목록 -> 수집 상태 순으로 브리핑 문서를 조립한다.

    Args:
        summarized_articles: Step 4 결과 기사 리스트 ("핵심" tier, 요약 포함)
        pending_review_articles: Step 3 결과 중 "확인 필요" tier 기사 리스트
        collection_stats: {source: {"today": int, "avg7d": float}} 형태의 소스별 수집 통계

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


def build_dashboard_html(
    summarized_articles: list[dict],
    pending_review_articles: list[dict],
    collection_stats: dict,
    target_date: str,
) -> str:
    """오늘의 핵심 -> 카테고리별 -> 확인 필요 -> 수집 상태 순으로 카드형 HTML 대시보드 페이지를 만든다.

    Args:
        summarized_articles: Step 4 결과 기사 리스트 ("핵심" tier, 요약 포함)
        pending_review_articles: Step 3 결과 중 "확인 필요" tier 기사 리스트
        collection_stats: {source: {"today": int, "avg7d": float}} 형태의 소스별 수집 통계
        target_date: YYYY-MM-DD 형식 날짜 문자열

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

    parts.append("<section><h2>오늘의 핵심</h2>")
    if not summarized_articles:
        parts.append("<p>오늘 핵심 기사가 없습니다.</p>")
    for article in summarized_articles:
        safe_url = _safe_url(article["url"])
        title = _esc(article["title"])
        source = _esc(article["source"])
        link = f'<a href="{safe_url}">{title}</a>' if safe_url else title
        parts.append('<article class="card">')
        if article.get("summary_fallback"):
            parts.append(f"<p>{link} ({source})</p>")
        else:
            tag = _esc(article.get("confirmation_tag", ""))
            parts.append(f"<p>{tag} <strong>{title}</strong></p>")
            parts.append(f"<p>{_esc(article['summary'])}</p>")
            parts.append(f'<p class="meta">{source} · {link}</p>')
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

    parts.append("</body></html>")
    return "\n".join(parts)


def build_index_html(dashboard_dir: Path, state_path: Path) -> str:
    """data/dashboard/*.html 파일 목록으로 날짜별 인덱스 페이지를 만든다.

    run_status.json의 마지막 실행 상태를 상단 배지로 보여준다 ("침묵 실패 방지").

    Args:
        dashboard_dir: data/dashboard 디렉토리 경로 (날짜별 html이 이미 생성돼 있어야 함)
        state_path: data/state/run_status.json 경로

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
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: left; }
tr.warn td { background: #fff3cd; }
.badge { display: inline-block; padding: 0.3rem 0.7rem; border-radius: 6px; font-size: 0.9rem; }
.badge.ok { background: #d4edda; color: #155724; }
.badge.fail { background: #f8d7da; color: #721c24; }
.badge.unknown { background: #e2e3e5; color: #383d41; }
a.latest { font-weight: bold; font-size: 1.1rem; }
"""


def run(
    summarized_articles: list[dict],
    pending_review_articles: list[dict],
    collection_stats: dict,
    archive_path: str,
    dashboard_dir: str,
    today: str,
    state_path: str,
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

    Returns:
        생성된 브리핑 마크다운 문서 문자열 (archive_path에도 저장)
    """
    briefing = build_briefing(summarized_articles, pending_review_articles, collection_stats)

    archive_path = Path(archive_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(briefing, encoding="utf-8")

    dashboard_dir = Path(dashboard_dir)
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    dashboard_html = build_dashboard_html(
        summarized_articles, pending_review_articles, collection_stats, today
    )
    (dashboard_dir / f"{today}.html").write_text(dashboard_html, encoding="utf-8")

    (dashboard_dir / "style.css").write_text(_DASHBOARD_CSS, encoding="utf-8")

    index_html = build_index_html(dashboard_dir, Path(state_path))
    (dashboard_dir / "index.html").write_text(index_html, encoding="utf-8")

    return briefing
