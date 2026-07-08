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


def run(
    summarized_articles: list[dict],
    pending_review_articles: list[dict],
    collection_stats: dict,
    output_path: str,
) -> str:
    """Step 5 진입점.

    Args:
        summarized_articles: data/summarized/YYYY-MM-DD.json 로드 결과
        pending_review_articles: data/classified/YYYY-MM-DD.json 중 "확인 필요" tier 기사
        collection_stats: 소스별 수집 통계
        output_path: data/archive/YYYY-MM-DD.md 저장 경로

    Returns:
        생성된 브리핑 문서 문자열 (output_path에도 저장)
    """
    briefing = build_briefing(summarized_articles, pending_review_articles, collection_stats)

    output_path = Path(output_path)
    output_path.write_text(briefing, encoding="utf-8")

    return briefing
