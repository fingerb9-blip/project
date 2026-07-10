"""Step 5. 조립 — 브리핑 마크다운 문서 및 대시보드 HTML 생성.

HTML/CSS 디자인은 대시보드_디자인_개편_명세_v2_SAVE스타일.md(§3 토큰, §9 CSS)를 따른다.
디자인은 네 곳에서만 산다: build_dashboard_html(), build_index_html(), build_archive_html(),
_DASHBOARD_CSS.
조회수·알림·커뮤니티·PDF·북마크는 §0 스코프 밖이라 구현하지 않는다.
"""

import html
import json
import math
import re
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from datetime import datetime as _datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

from src import issue_tracking, run_status

_ALLOWED_URL_SCHEMES = {"http", "https"}
_CATEGORY_ORDER = ["메모리", "파운드리", "장비·소재", "팹리스·설계", "규제·정책"]
_HIGHLIGHT_MAX_COUNT = 5
_BADGE_CONFIRM_ICONS = {"ok": "✓", "obs": "○", "mut": "–"}
_ALERT_SUPPRESS_WINDOW_HOURS = 24
_KOREAN_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
_KST = timezone(timedelta(hours=9))
_BRAND_NAME = "반도체브리핑"

# §3-2 소스 -> 배지 색 매핑. 미지정 소스는 기본 .badge(그레이)로 폴백된다.
_SOURCE_BADGE_CLASS = {
    "삼성전자 뉴스룸": "s-samsung",
    "SK하이닉스 뉴스룸": "s-hynix",
    "디일렉": "s-thelec",
    "EE Times": "s-eetimes",
    "DigiTimes": "s-digitimes",
    "Semiconductor Engineering": "s-semieng",
}

_SITE_FOOTER = (
    '<p class="site-footer">자동 생성 · 소스: 삼성전자 뉴스룸 · SK하이닉스 · 디일렉 · '
    "EE Times · DigiTimes · Semiconductor Engineering</p>"
)

# 실시간 트렌드 섹션(§3-3) — 정렬 순서대로 배정, "기타"는 마지막 그레이 고정.
_TREND_PALETTE = [
    "#6C5CE7", "#3D6FE6", "#1F7A6B", "#C2652A",
    "#A9790B", "#3B8B4E", "#B5457E", "#4E7CA1",
]
_TREND_OTHER_COLOR = "#B8BEC8"
_TREND_DONUT_RADIUS = 45


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


def _badge_class(source: str) -> str:
    """소스명을 §3-2 배지 색 클래스로 매핑한다. 미지정 소스는 빈 문자열(기본 그레이 .badge)."""
    return _SOURCE_BADGE_CLASS.get(source, "")


def _korean_weekday(iso_date: str) -> str:
    """YYYY-MM-DD 날짜의 한글 요일(월~일)을 반환한다."""
    return _KOREAN_WEEKDAYS[_date.fromisoformat(iso_date).weekday()]


def _korean_date_title(iso_date: str) -> str:
    """리포트 카드 제목용 'YYYY년 M월 D일 (요일)' 문자열을 만든다."""
    d = _date.fromisoformat(iso_date)
    return f"{d.year}년 {d.month}월 {d.day}일 ({_korean_weekday(iso_date)})"


def _korean_month_title(yyyymm: str) -> str:
    """'YYYY-MM' 문자열을 아카이브 월별 그룹 제목 'YYYY년 M월'로 변환한다."""
    year, month = yyyymm.split("-")
    return f"{year}년 {int(month)}월"


def _format_card_time(published_at: str | None) -> str:
    """기사 카드 배지 행 우측에 쓸 KST 'HH:MM' 시각. 파싱 불가하면 빈 문자열."""
    if not published_at:
        return ""
    try:
        dt = datetime.fromisoformat(published_at)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        return ""
    return dt.astimezone(_KST).strftime("%H:%M")


def _format_mtime_label(path: Path) -> str:
    """파일 mtime 기준 KST 'HH:MM 갱신' 문자열 (리포트 카드 타임스탬프용)."""
    dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).astimezone(_KST)
    return f"{dt.strftime('%H:%M')} 갱신"


def _list_dashboard_dates(dashboard_dir: Path, include: str | None = None) -> list[str]:
    """dashboard_dir에 이미 존재하는 날짜별 html 목록을 최신순으로 반환한다.

    Args:
        dashboard_dir: data/dashboard 디렉토리 경로
        include: 아직 파일로 쓰이지 않았더라도 목록에 포함할 날짜 (오늘 페이지 생성 시 사용)
    """
    dates = {p.stem for p in dashboard_dir.glob("*.html") if p.stem not in ("index", "archive")}
    if include:
        dates.add(include)
    return sorted(dates, reverse=True)


def _build_date_select(all_dates: list[str], target_date: str) -> str:
    """다른 날짜 브리핑으로 바로 이동할 수 있는 드롭다운을 만든다 (§5-2, 선택 요소)."""
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


_DATE_SELECT_RE = re.compile(r'<select class="date-select".*?</select>', re.S)


def _refresh_date_selects(dashboard_dir: Path, all_dates: list[str]) -> None:
    """기존 데일리 페이지들의 날짜 드롭다운을 최신 날짜 목록으로 교체한다.

    각 페이지의 드롭다운은 생성 시점의 날짜 목록으로 굳어 있어, 새 날짜가 추가돼도
    이전 페이지에서는 최신 날짜로 이동할 수 없었다(예: 7/9 리포트 드롭다운에 7/10이
    없음). 페이지 본문은 그대로 두고 <select class="date-select"> 블록만 교체한다.
    """
    for path in dashboard_dir.glob("*.html"):
        if path.stem in ("index", "archive"):
            continue
        html_text = path.read_text(encoding="utf-8")
        new_select = _build_date_select(all_dates, path.stem)
        new_html, count = _DATE_SELECT_RE.subn(new_select, html_text, count=1)
        if count and new_html != html_text:
            path.write_text(new_html, encoding="utf-8")


def _split_categories(raw_categories: list[str]) -> list[str]:
    """카테고리 문자열 하나에 여러 카테고리가 공백으로 붙어 온 경우(예: "메모리 장비·소재")를
    분리한다. config/categories.yaml의 카테고리명에는 공백이 없어 안전하게 분리할 수 있다.
    """
    return [name for raw in raw_categories for name in raw.split()]


def _ordered_categories(articles: list[dict]) -> list[str]:
    """카테고리 pill 필터에 쓸 카테고리 목록을 config/categories.yaml 순서대로 정렬한다."""
    present: list[str] = []
    for article in articles:
        for category in _split_categories(article.get("category") or []):
            if category not in present:
                present.append(category)
    ordered = [c for c in _CATEGORY_ORDER if c in present]
    ordered += [c for c in present if c not in _CATEGORY_ORDER]
    return ordered


def _build_appbar() -> str:
    """전 페이지 공통 헤더: 브랜드 스티커 태그 (§4-1). 알림 벨은 스코프 밖이라 생략."""
    return f'<div class="appbar"><span class="brand">{_esc(_BRAND_NAME)}</span></div>'


def _build_search_bar() -> str:
    """전 페이지 공통 검색바 (§4-1·§4-3). #feed .card를 대상으로 클라이언트 필터링한다."""
    return (
        '<div class="search">'
        '<input id="q" type="search" placeholder="뉴스 태그·제목·내용을 검색해 주세요" '
        'aria-label="뉴스 검색">'
        '<span class="i">🔍</span>'
        "</div>"
    )


def _build_filter_bar(categories: list[str]) -> str:
    """'오늘의 핵심' 카드를 카테고리로 거를 수 있는 pill 필터 바 (§4-4).

    JS가 꺼져 있어도 버튼은 무해하고 카드는 전부 보인다 (점진적 향상).
    """
    if not categories:
        return ""
    parts = ['<div class="filter" role="group" aria-label="카테고리 필터">']
    parts.append('<button type="button" data-cat="all" aria-pressed="true">전체</button>')
    for category in categories:
        parts.append(
            f'<button type="button" data-cat="{_esc(category)}" aria-pressed="false">'
            f"{_esc(category)}</button>"
        )
    parts.append("</div>")
    return "".join(parts)


_DASHBOARD_SCRIPT = """\
<script>
function isNoised(id){return !!(id&&localStorage.getItem('noise:'+id));}
function applyFilters(){
  var q=(document.getElementById('q')||{}).value||'';
  q=q.trim().toLowerCase();
  var active=document.querySelector('.filter button[aria-pressed="true"]');
  var cat=active?active.dataset.cat:'all';
  var deepOnly=(document.getElementById('deep-tech-filter')||{}).checked||false;
  document.querySelectorAll('#feed .card').forEach(function(c){
    var okCat=(cat==='all')||((c.dataset.categories||'').split(' ').indexOf(cat)>-1);
    var okQ=!q||((c.dataset.text||'').indexOf(q)>-1);
    var t=c.dataset.sourceType;
    var okDeep=!deepOnly||(t==='학회');
    var okNoise=!isNoised(c.dataset.articleId);
    c.style.display=(okCat&&okQ&&okDeep&&okNoise)?'':'none';
  });
}
function applyNoise(){
  // '오늘의 핵심' 하이라이트 카드는 #feed 밖이라 applyFilters가 건드리지 않으므로 따로 숨긴다.
  document.querySelectorAll('.highlight-card').forEach(function(c){
    if(isNoised(c.dataset.articleId)) c.style.display='none';
  });
}
document.querySelectorAll('.filter button').forEach(function(b){
  b.addEventListener('click',function(){
    document.querySelectorAll('.filter button').forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});
    applyFilters();
  });
});
var qi=document.getElementById('q'); if(qi) qi.addEventListener('input',applyFilters);
var dtf=document.getElementById('deep-tech-filter'); if(dtf) dtf.addEventListener('change',applyFilters);
document.querySelectorAll('.noise-btn').forEach(function(b){
  b.addEventListener('click',function(){
    var id=b.dataset.articleId;
    if(id) localStorage.setItem('noise:'+id,'1');
    applyFilters();
    applyNoise();
  });
});
applyFilters();
applyNoise();
</script>
"""


def _build_article_card(article: dict) -> str:
    """기사 하나를 §4-5 뉴스 카드(소스 배지+태그 칩+카테고리 칩+시각 -> 제목 -> 요약 -> 원문 링크)로
    렌더링한다. _esc()/_safe_url()을 반드시 통과시킨다 — RSS/뉴스 텍스트는 신뢰 불가 입력이다.

    Args:
        article: 요약 결과 기사 dict. source_type이 있으면(학회 등) 배지로 표시하고
            데일리 페이지의 "학회만 보기" 필터가 이 값을 기준으로 카드를 감춘다.
    """
    article_categories = _split_categories(article.get("category") or ["미분류"])
    cats_attr = _esc(" ".join(article_categories))
    safe_url = _safe_url(article["url"])
    title = _esc(article["title"])
    source = _esc(article["source"])
    source_type = article.get("source_type", "언론")
    link_open = f'<a href="{safe_url}">' if safe_url else ""
    link_close = "</a>" if safe_url else ""

    if article.get("summary_fallback"):
        confirm_class, confirm_label = "mut", "요약 없음"
    else:
        tag = article.get("confirmation_tag") or ""
        if "확정" in tag:
            confirm_class = "ok"
        elif "관측" in tag:
            confirm_class = "obs"
        else:
            confirm_class = "mut"
        confirm_label = tag

    search_text = " ".join(
        [article["source"], article["title"], article.get("summary") or ""]
    ).lower()

    parts = [
        f'<article class="card" data-article-id="{_esc(article.get("id", ""))}" '
        f'data-categories="{cats_attr}" data-text="{_esc(search_text)}" '
        f'data-source-type="{_esc(source_type)}">'
    ]
    parts.append('<div class="row">')
    parts.append(f'<span class="badge {_badge_class(article["source"])}">{source}</span>')
    if source_type and source_type != "언론":
        parts.append(f'<span class="chip badge-type">{_esc(source_type)}</span>')
    if confirm_label:
        icon = _BADGE_CONFIRM_ICONS[confirm_class]
        parts.append(f'<span class="badge-confirm {confirm_class}">{icon} {_esc(confirm_label)}</span>')
    if article.get("summary_extractive"):
        parts.append('<span class="chip badge-type">발췌</span>')
    for category in article_categories:
        parts.append(f'<span class="badge-category">{_esc(category)}</span>')
    for stock_entry in article.get("related_stock") or []:
        change_pct = stock_entry["change_pct"]
        direction_class = "stock-up" if change_pct >= 0 else "stock-down"
        arrow = "▲" if change_pct >= 0 else "▼"
        parts.append(
            f'<span class="chip {direction_class}">{_esc(stock_entry["name"])} '
            f'{arrow}{abs(change_pct):.1f}%</span>'
        )
    time_label = _format_card_time(article.get("published_at"))
    parts.append('<span class="spacer"></span>')
    if time_label:
        parts.append(f'<span class="time">{_esc(time_label)}</span>')
    parts.append("</div>")
    parts.append(f'<p class="title">{link_open}{title}{link_close}</p>')
    if not article.get("summary_fallback"):
        parts.append(f'<p class="summary">{_esc(article["summary"])}</p>')
    parts.append('<div class="cardfoot">')
    if safe_url:
        parts.append(f'<a href="{safe_url}">원문 보기 ↗</a>')
    parts.append(
        f'<button type="button" class="noise-btn" data-article-id="{_esc(article.get("id", ""))}">'
        "노이즈로 표시</button>"
    )
    parts.append("</div>")
    parts.append("</article>")
    return "".join(parts)


def _highlight_sort_timestamp(article: dict) -> float:
    """최신순 정렬용 published_at epoch 타임스탬프. 파싱 불가·누락 시 가장 오래된 값(0.0)으로 취급한다."""
    published_at = article.get("published_at")
    if not published_at:
        return 0.0
    try:
        dt = datetime.fromisoformat(published_at)
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def select_highlights(articles: list[dict], max_count: int = _HIGHLIGHT_MAX_COUNT) -> list[dict]:
    """"오늘의 핵심" 상단에 노출할 하이라이트 기사를 선정한다.

    선정 기준: (a) confirmation_tag에 "확정"이 포함된 기사 우선, (b) 이미 선정된 기사와
    카테고리가 겹치지 않는 기사 우선(다양성 확보), (c) 최신순. 요약이 없는 기사
    (summary_fallback 또는 summary 미기재)는 1·2단계 후보에서는 제외하지만, "핵심" tier
    기사 자체가 max_count개 이상 있는데도 요약 품질 필터 때문에 결과가 부족해지는 것을
    막기 위해 3단계에서 요약 유무와 무관하게 최신순으로 채워 넣는다("핵심" 섹션이 뉴스가
    있는 날에도 비어 보이는 문제 방지).

    Args:
        articles: Step 4 결과 기사 리스트 ("핵심" tier, 요약 포함)
        max_count: 최대 선정 개수 (기본 5)

    Returns:
        하이라이트로 선정된 기사 리스트. "핵심" tier 기사 자체가 max_count보다 적을 때만
        max_count보다 적게 반환한다.
    """
    candidates = [
        article for article in articles
        if not article.get("summary_fallback") and article.get("summary")
    ]
    candidates.sort(
        key=lambda a: (
            "확정" not in (a.get("confirmation_tag") or ""),
            -_highlight_sort_timestamp(a),
        )
    )

    selected: list[dict] = []
    used_categories: set[str] = set()
    leftover: list[dict] = []
    for article in candidates:
        article_categories = set(article.get("category") or [])
        if article_categories & used_categories:
            leftover.append(article)
            continue
        selected.append(article)
        used_categories |= article_categories
        if len(selected) >= max_count:
            return selected

    for article in leftover:
        if len(selected) >= max_count:
            return selected
        selected.append(article)

    if len(selected) < max_count:
        selected_ids = {id(article) for article in selected}
        remaining = [article for article in articles if id(article) not in selected_ids]
        remaining.sort(key=_highlight_sort_timestamp, reverse=True)
        for article in remaining:
            if len(selected) >= max_count:
                break
            selected.append(article)

    return selected


def _build_highlight_card(article: dict) -> str:
    """하이라이트 카드 — 제목 + 1줄 요약 + 확정/관측 태그 + 카테고리 칩으로 축약 렌더링한다.
    _esc()/_safe_url()을 반드시 통과시킨다 — RSS/뉴스 텍스트는 신뢰 불가 입력이다.
    """
    safe_url = _safe_url(article["url"])
    title = _esc(article["title"])
    link_open = f'<a href="{safe_url}">' if safe_url else ""
    link_close = "</a>" if safe_url else ""

    tag = article.get("confirmation_tag") or ""
    if "확정" in tag:
        confirm_class = "ok"
    elif "관측" in tag:
        confirm_class = "obs"
    else:
        confirm_class = "mut"

    parts = [f'<article class="highlight-card" data-article-id="{_esc(article.get("id", ""))}">']
    parts.append('<div class="row">')
    if tag:
        icon = _BADGE_CONFIRM_ICONS[confirm_class]
        parts.append(f'<span class="badge-confirm {confirm_class}">{icon} {_esc(tag)}</span>')
    if article.get("summary_extractive"):
        parts.append('<span class="chip badge-type">발췌</span>')
    for category in _split_categories(article.get("category") or []):
        parts.append(f'<span class="badge-category">{_esc(category)}</span>')
    parts.append("</div>")
    parts.append(f'<p class="title">{link_open}{title}{link_close}</p>')
    summary = article.get("summary")
    if summary:
        parts.append(f'<p class="summary">{_esc(summary)}</p>')
    else:
        parts.append('<p class="summary mut">요약 준비 중 — 원문에서 확인하세요.</p>')
    parts.append("</article>")
    return "".join(parts)


def _build_highlight_strip(articles: list[dict]) -> str:
    """select_highlights() 결과를 가로 스크롤 하이라이트 스트립으로 렌더링한다.
    후보가 없으면 빈 문자열(빈 컨테이너를 남기지 않는다).
    """
    if not articles:
        return ""
    parts = ['<div class="highlight-strip">']
    for article in articles:
        parts.append(_build_highlight_card(article))
    parts.append("</div>")
    return "".join(parts)


def build_dashboard_html(
    summarized_articles: list[dict],
    pending_review_articles: list[dict],
    collection_stats: dict,
    target_date: str,
    all_dates: list[str] | None = None,
    active_issues: list[dict] | None = None,
    updated_at: str | None = None,
) -> str:
    """헤더(브랜드+검색) -> pill 필터 -> 오늘의 핵심(뉴스 카드) -> 확인 필요 -> 수집 상태 ->
    진행 중 이슈 순으로 데일리 대시보드 페이지를 만든다 (§5-2 레이아웃, SAVE 스타일).

    Args:
        summarized_articles: Step 4 결과 기사 리스트 ("핵심" tier, 요약 포함)
        pending_review_articles: Step 3 결과 중 "확인 필요" tier 기사 리스트
        collection_stats: {source: {"today": int, "avg7d": float}} 형태의 소스별 수집 통계
        target_date: YYYY-MM-DD 형식 날짜 문자열
        all_dates: 날짜 드롭다운에 표시할 전체 날짜 목록 (없으면 target_date만 표시)
        active_issues: data/state/issues.json 중 status="진행중"인 이슈 리스트 (Phase 3)
        updated_at: rebuild_dashboard.py가 과거 페이지를 재생성할 때 원본 파일 mtime을 넘겨
            받기 위한 자리로 시그니처를 유지한다. v2 레이아웃(§5-2)은 데일리 페이지에
            페이지 단위 "갱신" 타임스탬프를 두지 않으므로(카드별 시각·리포트 카드 쪽에서
            표시) 현재는 렌더링에 쓰이지 않는다.

    Returns:
        단일 HTML 문서 문자열
    """
    all_dates = all_dates or [target_date]
    del updated_at  # 시그니처 호환용 — v2 데일리 레이아웃엔 표시할 슬롯이 없다.

    parts = [
        "<!doctype html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>반도체 뉴스 브리핑 {_esc(target_date)}</title>",
        '<link rel="stylesheet" href="style.css">',
        "</head><body>",
        _build_appbar(),
        _build_search_bar(),
        '<p class="row"><a href="index.html">&larr; 전체 목록</a>'
        '<span class="spacer"></span>'
        + _build_date_select(all_dates, target_date)
        + "</p>",
    ]

    categories = _ordered_categories(summarized_articles)
    parts.append(_build_filter_bar(categories))

    parts.append('<h2 class="sec">오늘의 핵심</h2>')
    parts.append(_build_highlight_strip(select_highlights(summarized_articles)))
    parts.append(
        '<label class="filter-toggle"><input type="checkbox" id="deep-tech-filter"> '
        "학회만 보기</label>"
    )
    if not summarized_articles:
        parts.append('<p class="summary">오늘 핵심 기사가 없습니다.</p>')
    parts.append('<div id="feed">')
    for article in summarized_articles:
        parts.append(_build_article_card(article))
    parts.append("</div>")

    parts.append('<details class="card">')
    parts.append(f"<summary>확인 필요 <span class=\"chip\">{len(pending_review_articles)}건</span></summary>")
    if not pending_review_articles:
        parts.append('<p class="summary">없음</p>')
    else:
        parts.append('<ul class="pending-list">')
        for article in pending_review_articles:
            safe_url = _safe_url(article["url"])
            title = _esc(article["title"])
            link = f'<a href="{safe_url}">{title}</a>' if safe_url else title
            parts.append(f'<li>{link} <span class="time">({_esc(article["source"])})</span></li>')
        parts.append("</ul>")
    parts.append("</details>")

    parts.append('<h2 class="sec">수집 상태</h2>')
    parts.append('<div class="table-wrap"><table>')
    parts.append('<tr><th>소스</th><th class="num">오늘</th><th class="num">7일 평균</th></tr>')
    for source, stats in collection_stats.items():
        today_count = stats.get("today", 0)
        avg7d = stats.get("avg7d", 0)
        row_class = ' class="warn"' if avg7d > 0 and today_count < avg7d * 0.3 else ""
        parts.append(
            f"<tr{row_class}><td>{_esc(source)}</td>"
            f'<td class="num">{today_count}</td><td class="num">{avg7d:.1f}</td></tr>'
        )
    parts.append("</table></div>")

    if active_issues:
        parts.append('<h2 class="sec">진행 중 이슈</h2>')
        for issue in active_issues:
            article_count = len(issue.get("related_article_ids") or [])
            parts.append('<article class="card">')
            parts.append(f'<div class="row"><span class="chip">{_esc(issue.get("entity", ""))}</span></div>')
            parts.append(f'<p class="title">{_esc(issue.get("title", ""))}</p>')
            parts.append(
                f'<p class="time">{_esc(issue.get("first_seen", ""))} ~ '
                f'{_esc(issue.get("last_updated", ""))} · 관련 기사 {article_count}건</p>'
            )
            if issue.get("progress_summary"):
                parts.append(f'<p class="summary">경과 요약: {_esc(issue["progress_summary"])}</p>')
            parts.append("</article>")

    parts.append(_SITE_FOOTER)
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
        _build_appbar(),
        '<p><a href="../index.html">&larr; 전체 목록</a></p>',
        '<article class="card">',
        f'<div class="row"><span class="chip">{_esc(issue.get("entity", ""))}</span></div>',
        f"<p class=\"title\">🚨 {_esc(issue.get('tag', ''))} {_esc(title)}</p>",
        f'<p class="time">최초 감지: {_esc(issue.get("first_seen", ""))} · '
        f'최근 갱신: {_esc(issue.get("last_updated", ""))}</p>',
    ]
    if issue.get("progress_summary"):
        parts.append(f'<p class="summary">{_esc(issue["progress_summary"])}</p>')
    parts.append("</article>")
    parts.append(_SITE_FOOTER)
    parts.append("</body></html>")
    return "\n".join(parts)


def _build_report_card(dashboard_dir: Path, iso_date: str) -> str:
    """§4-6 리포트 카드 (인덱스 아카이브 리스트 항목). PDF 다운로드는 스코프 밖(§0)이라 넣지 않는다."""
    html_path = dashboard_dir / f"{iso_date}.html"
    time_label = _format_mtime_label(html_path) if html_path.exists() else ""
    parts = ['<div class="card report" data-text="' + _esc(iso_date.lower()) + '">']
    parts.append('<div class="row"><span class="chip">리포트</span><span class="spacer"></span>')
    if time_label:
        parts.append(f'<span class="time">{_esc(time_label)}</span>')
    parts.append("</div>")
    parts.append(f'<p class="datetitle">{_esc(_korean_date_title(iso_date))}</p>')
    parts.append('<div class="actions">')
    parts.append(f'<a href="{_esc(iso_date)}.html">📄 리포트 읽기</a>')
    parts.append("</div>")
    parts.append("</div>")
    return "".join(parts)


def build_archive_html(dashboard_dir: Path) -> str:
    """data/dashboard/*.html 전체를 월별로 그룹핑해 보여주는 아카이브 페이지를 만든다.

    build_index_html()의 리포트 목록과 달리 전체 기간을 대상으로 하며, index.html의
    "지난 리포트 전체보기" 링크로 진입한다. 별도 데이터 소스 없이 dashboard_dir에 이미
    존재하는 파일명을 스캔해 그룹핑한다 (build_index_html()과 동일한 방식).

    검색창은 index.html이 이미 쓰는 _DASHBOARD_SCRIPT를 그대로 재사용한다 — 새 스크립트를
    만들 필요 없이, 리포트 카드를 하나의 id="feed" 컨테이너에 담기만 하면 #feed .card
    대상 텍스트 검색이 그대로 동작한다(_build_report_card()가 이미 data-text에 날짜를
    채워둔다). 이 페이지에 없는 .filter/#deep-tech-filter 요소는 스크립트의 ||{} 폴백으로
    안전하게 무시된다 — index.html에서 이미 검증된 패턴이다.

    Args:
        dashboard_dir: data/dashboard 디렉토리 경로 (날짜별 html이 이미 생성돼 있어야 함)

    Returns:
        단일 HTML 문서 문자열
    """
    dates = sorted(
        (p.stem for p in dashboard_dir.glob("*.html") if p.stem not in ("index", "archive")),
        reverse=True,
    )

    by_month: dict[str, list[str]] = {}
    for iso_date in dates:
        by_month.setdefault(iso_date[:7], []).append(iso_date)

    parts = [
        "<!doctype html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>지난 리포트 전체보기 - 반도체 뉴스 브리핑</title>",
        '<link rel="stylesheet" href="style.css">',
        "</head><body>",
        _build_appbar(),
        _build_search_bar(),
        '<p class="row"><a href="index.html">&larr; 최신 브리핑으로</a></p>',
    ]

    if not by_month:
        parts.append('<p class="summary">아직 생성된 브리핑이 없습니다.</p>')
    else:
        parts.append('<div id="feed">')
        for yyyymm in sorted(by_month, reverse=True):
            parts.append(f'<h2 class="sec">{_esc(_korean_month_title(yyyymm))}</h2>')
            for iso_date in by_month[yyyymm]:
                parts.append(_build_report_card(dashboard_dir, iso_date))
        parts.append("</div>")

    parts.append(_SITE_FOOTER)
    parts.append(_DASHBOARD_SCRIPT)
    parts.append("</body></html>")
    return "\n".join(parts)


def load_latest_radar(radar_dir: Path) -> dict | None:
    """data/radar/weekly-*.json 중 가장 최근 파일을 읽는다. 없으면 None.

    Args:
        radar_dir: data/radar 디렉토리 경로

    Returns:
        가장 최근 주간 레이더 데이터 dict, 또는 파일이 없으면 None
    """
    radar_dir = Path(radar_dir)
    if not radar_dir.exists():
        return None
    files = sorted(radar_dir.glob("weekly-*.json"), reverse=True)
    if not files:
        return None
    with files[0].open(encoding="utf-8") as f:
        return json.load(f)


def load_latest_trend(trends_dir: Path) -> dict | None:
    """data/trends/*.json 중 가장 최근 파일을 읽는다. 없으면 None.

    step1_5_anomaly_detect.py가 index.html을 재생성할 때도 언급량 트렌드 섹션이
    사라지지 않도록 load_latest_radar()와 동일한 패턴으로 디스크에서 최신 데이터를 읽는다.

    Args:
        trends_dir: data/trends 디렉토리 경로

    Returns:
        가장 최근 언급량 트렌드 데이터 dict, 또는 파일이 없으면 None
    """
    trends_dir = Path(trends_dir)
    if not trends_dir.exists():
        return None
    files = sorted(trends_dir.glob("*.json"), reverse=True)
    if not files:
        return None
    with files[0].open(encoding="utf-8") as f:
        return json.load(f)


def build_radar_section_html(radar_data: dict | None) -> str:
    """경쟁 구도 레이더 주간 데이터를 index.html 섹션으로 렌더링한다.

    기업별 언급량은 CSS 너비 기반 가로 막대 그래프로, 톤 비율은 표로,
    최다 언급 이슈와 주간 해설을 함께 보여준다.

    Args:
        radar_data: radar_weekly.run() 결과 dict
            ({week, mentions, tone, top_issues, commentary})

    Returns:
        섹션 HTML 조각 (radar_data가 비어 있으면 빈 문자열)
    """
    if not radar_data:
        return ""

    mentions = radar_data.get("mentions") or {}
    max_mentions = max(mentions.values(), default=0)

    parts = [f"<section><h2>경쟁 구도 레이더 ({_esc(radar_data.get('week', ''))})</h2>"]

    parts.append('<div class="radar-bars">')
    for company, count in mentions.items():
        width = int(count / max_mentions * 100) if max_mentions > 0 else 0
        parts.append(
            f'<div class="radar-row"><span class="radar-label">{_esc(company)}</span>'
            f'<span class="radar-bar" style="width:{width}%"></span>'
            f'<span class="radar-count">{_esc(count)}</span></div>'
        )
    parts.append("</div>")

    tone = radar_data.get("tone") or {}
    if tone:
        parts.append("<table><tr><th>기업</th><th>긍정</th><th>부정</th><th>중립</th></tr>")
        for company, t in tone.items():
            parts.append(
                f"<tr><td>{_esc(company)}</td>"
                f"<td>{_esc(round(t.get('pos', 0) * 100))}%</td>"
                f"<td>{_esc(round(t.get('neg', 0) * 100))}%</td>"
                f"<td>{_esc(round(t.get('neu', 0) * 100))}%</td></tr>"
            )
        parts.append("</table>")

    top_issues = radar_data.get("top_issues") or []
    if top_issues:
        parts.append("<h3>최다 언급 이슈</h3><ul>")
        for issue in top_issues:
            parts.append(f"<li>{_esc(issue)}</li>")
        parts.append("</ul>")

    if radar_data.get("commentary"):
        parts.append(f"<p>{_esc(radar_data['commentary'])}</p>")

    parts.append("</section>")
    return "".join(parts)


def build_mention_trend_section_html(trend_data: dict | None, stage: str) -> str:
    """기업/기술 키워드 언급량 트렌드를 index.html 섹션으로 렌더링한다 (Phase 5).

    stage가 "preview"면 제목에 "(참고용)"을 붙인다. trend_data가 없으면 빈 문자열을 반환한다
    (호출부가 cold_start_stage == "hidden"일 때 넘기지 않는다).

    Args:
        trend_data: step_mention_trend.run() 결과 ({"date","companies","keywords"})
        stage: step_mention_trend.cold_start_stage() 결과

    Returns:
        섹션 HTML 조각 (trend_data가 비어 있으면 빈 문자열)
    """
    if not trend_data:
        return ""

    label = " (참고용)" if stage == "preview" else ""
    parts = [f"<section><h2>기업·기술 키워드 언급량 트렌드{_esc(label)}</h2>"]

    for title, field in (("기업", "companies"), ("기술 키워드", "keywords")):
        entries = trend_data.get(field) or []
        if not entries:
            continue
        parts.append(f"<h3>{_esc(title)}</h3>")
        parts.append('<div class="radar-bars">')
        max_count = max((e["count"] for e in entries), default=0)
        for entry in entries:
            width = int(entry["count"] / max_count * 100) if max_count > 0 else 0
            spike_chip = ' <span class="chip warn-chip">급증</span>' if entry.get("is_spike") else ""
            parts.append(
                f'<div class="radar-row"><span class="radar-label">{_esc(entry["name"])}</span>'
                f'<span class="radar-bar" style="width:{width}%"></span>'
                f'<span class="radar-count">{_esc(entry["count"])}</span>{spike_chip}</div>'
            )
        parts.append("</div>")

    parts.append("</section>")
    return "".join(parts)


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


def _load_tracked_terms() -> dict[str, list[str]]:
    """실시간 트렌드 집계용 추적어 사전을 만든다 (§1).

    company_aliases.yaml의 기업 정식명(별칭 중 첫 번째)마다 전체 별칭 목록을,
    keywords.yaml whitelist의 토픽 키워드마다 자기 자신 하나짜리 목록을 매칭 후보로 둔다.
    blacklist·risk_keywords는 집계에서 제외한다.
    """
    config_dir = Path(__file__).resolve().parent.parent / "config"
    terms: dict[str, list[str]] = {}

    aliases_path = config_dir / "company_aliases.yaml"
    if aliases_path.exists():
        with aliases_path.open(encoding="utf-8") as f:
            aliases_config = yaml.safe_load(f) or {}
        for entity in aliases_config.values():
            entity_aliases = entity.get("aliases") or []
            if entity_aliases:
                terms[entity_aliases[0]] = entity_aliases

    keywords_path = config_dir / "keywords.yaml"
    if keywords_path.exists():
        with keywords_path.open(encoding="utf-8") as f:
            keywords_config = yaml.safe_load(f) or {}
        for topic_keywords in (keywords_config.get("whitelist") or {}).values():
            for keyword in topic_keywords or []:
                terms.setdefault(keyword, [keyword])

    return terms


def _compute_keyword_trends(articles: list[dict], *, top_n: int = 8) -> list[dict]:
    """§1 집계 규칙. 기업(별칭 매칭)·토픽 키워드를 합쳐 언급 빈도를 내림차순 집계한다.

    각 기사는 추적어 하나당 최대 1회만 카운트된다(같은 기사 내 반복 언급은 중복 집계
    하지 않음). 반환되는 pct의 분모는 "추적어 총 언급 수"이며, 기사 한 건이 여러
    추적어에 매칭되면 각각 카운트되므로 총합이 기사 수보다 클 수 있다.

    Args:
        articles: 제목(title)·요약(summary)을 담은 기사 dict 리스트
        top_n: 개별 표시할 상위 추적어 수 (나머지는 "기타"로 합산)

    Returns:
        [{"keyword", "count", "pct", "color"}, ...] 내림차순 리스트 (데이터 없으면 빈 리스트)
    """
    terms = _load_tracked_terms()
    counts: dict[str, int] = {}
    for article in articles:
        text = f"{article.get('title', '')} {article.get('summary', '')}"
        for canonical, term_aliases in terms.items():
            if any(alias in text for alias in term_aliases):
                counts[canonical] = counts.get(canonical, 0) + 1

    total = sum(counts.values())
    if total == 0:
        return []

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    top, rest = ranked[:top_n], ranked[top_n:]

    trends = [
        {
            "keyword": keyword,
            "count": count,
            "pct": round(count / total * 100, 1),
            "color": _TREND_PALETTE[i % len(_TREND_PALETTE)],
        }
        for i, (keyword, count) in enumerate(top)
    ]

    rest_count = sum(count for _, count in rest)
    if rest_count:
        trends.append(
            {
                "keyword": "기타",
                "count": rest_count,
                "pct": round(rest_count / total * 100, 1),
                "color": _TREND_OTHER_COLOR,
            }
        )
    return trends


def _donut_svg(trends: list[dict], total_count: int) -> str:
    """§4 도넛 SVG 수학. 내림차순 trends를 12시 방향에서 시계방향으로 그린다.

    원둘레 C = 2πr(r=45)이고, 세그먼트 i의 길이는 pct_i/100 * C, dashoffset은
    이전까지 누적 비율만큼 앞으로 이동시킨 음수 값이다. SVG 수치는 포맷된 float만
    삽입하고(문자열 삽입 금지), <title>에 들어가는 키워드 라벨은 _esc()로 이스케이프한다.
    """
    circumference = 2 * math.pi * _TREND_DONUT_RADIUS
    cumulative = 0.0
    segments = []
    for trend in trends:
        fraction = trend["pct"] / 100.0
        seg_len = fraction * circumference
        gap_len = circumference - seg_len
        dashoffset = -(cumulative * circumference)
        segments.append(
            f'<circle cx="60" cy="60" r="{_TREND_DONUT_RADIUS}" fill="none" stroke="{trend["color"]}" '
            f'stroke-width="18" stroke-dasharray="{seg_len:.3f} {gap_len:.3f}" '
            f'stroke-dashoffset="{dashoffset:.3f}"/>'
        )
        cumulative += fraction
    ring = "".join(segments)
    title = "실시간 트렌드: " + ", ".join(f"{t['keyword']} {t['pct']}%" for t in trends)
    return (
        '<svg viewBox="0 0 120 120" role="img" width="160" height="160" class="donut">'
        f"<title>{_esc(title)}</title>"
        f'<g transform="rotate(-90 60 60)">{ring}</g>'
        f'<text x="60" y="58" text-anchor="middle" class="donut-num">{total_count}</text>'
        '<text x="60" y="72" text-anchor="middle" class="donut-cap">건</text>'
        "</svg>"
    )


def render_trend_section(trends: list[dict], total_count: int) -> str:
    """§2 레이아웃. 왼쪽 도넛(§4) + 오른쪽 가로 막대(§3-2, 도넛과 색 1:1 일치)를 카드로
    조립한다. trends가 비면(총합 0) 섹션 전체를 생략한다.
    """
    if not trends:
        return ""
    bars = "".join(
        f'<div class="tbar"><span class="k">{_esc(t["keyword"])}</span>'
        f'<span class="track"><span class="fill" style="width:{t["pct"]}%;background:{t["color"]}"></span></span>'
        f'<span class="p">{t["pct"]}%</span></div>'
        for t in trends
    )
    return (
        '<section class="trend"><div class="trend-head">'
        '<h2 class="sec">실시간 트렌드</h2><span class="sub">최신 브리핑 기준</span></div>'
        f'<div class="trend-body"><div class="trend-donut">{_donut_svg(trends, total_count)}</div>'
        f'<div class="trend-bars">{bars}</div></div></section>'
    )


def _load_latest_trend_articles(
    dashboard_dir: Path, latest_date: str, issues_path: Path | None
) -> list[dict]:
    """트렌드 집계용 최신 날짜 기사를 불러온다 (§1: summarized+classified, 없으면 issues.json 보조).

    dashboard_dir(data/dashboard)의 형제 디렉토리인 data/summarized, data/classified에서
    해당 날짜 JSON을 읽는다. 둘 다 없으면(예: 로컬에 원본 JSON을 보관하지 않는 환경)
    issues.json의 entity/title로 축약 계산한다.
    """
    data_dir = Path(dashboard_dir).parent
    articles: list[dict] = []
    for sub in ("summarized", "classified"):
        path = data_dir / sub / f"{latest_date}.json"
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8") as f:
                articles.extend(json.load(f))
        except (OSError, json.JSONDecodeError):
            continue

    if articles:
        return articles

    if issues_path is not None:
        issues = issue_tracking.load_issues(issues_path)
        return [
            {"title": issue.get("title", ""), "summary": issue.get("entity", "")}
            for issue in issues
        ]

    return []


def build_index_html(
    dashboard_dir: Path,
    state_path: Path,
    issues_path: Path | None = None,
    now: str | None = None,
    latest_core_count: int | None = None,
    latest_headlines: list[str] | None = None,
    radar_data: dict | None = None,
    pending_keywords: list[dict] | None = None,
    mention_trend_data: dict | None = None,
    cold_start_stage: str = "active",
) -> str:
    """헤더(브랜드+검색) -> 히어로 배너(최신 브리핑) -> 리포트 카드 목록 순으로 인덱스 페이지를
    만든다 (§5-1 레이아웃, SAVE 스타일). 조회수·알림 등은 §0 스코프 밖이라 표시하지 않는다.

    run_status.json의 마지막 실행 상태를 히어로 배너 하단 상태 문구로 보여준다
    ("침묵 실패 방지"). issues_path가 주어지면 24시간 이내 확정된 속보를 상단 배너로도 보여준다.
    pending_keywords가 주어지면 관리자용 키워드 후보 섹션을 함께 보여준다.

    Args:
        dashboard_dir: data/dashboard 디렉토리 경로 (날짜별 html이 이미 생성돼 있어야 함)
        state_path: data/state/run_status.json 경로
        issues_path: data/state/issues.json 경로 (속보 배너용, 선택)
        now: 현재 시각 ISO8601 문자열 (테스트용, 기본값은 UTC 현재 시각)
        latest_core_count: 최신 날짜의 "오늘의 핵심" 기사 수 (현재 v2 히어로에는 표시하지
            않지만 v1과의 호출 호환을 위해 인자는 유지한다)
        latest_headlines: 최신 날짜의 헤드라인 미리보기 목록 (위와 동일한 이유로 유지, 미사용)
        radar_data: 경쟁 구도 레이더 주간 데이터 (Phase 4, 선택). index.html 상단 섹션에 포함된다.
        pending_keywords: config/keywords_pending.yaml의 candidates 리스트 (관리자 섹션용, 선택)
        mention_trend_data: step_mention_trend.run() 결과 (Phase 5, 선택). cold_start_stage가
            "hidden"이면 호출부가 아예 넘기지 않아 섹션이 렌더링되지 않는다.
        cold_start_stage: step_mention_trend.cold_start_stage() 결과. "preview"면 섹션 제목에
            "(참고용)" 라벨이 붙는다.

    Returns:
        단일 HTML 문서 문자열
    """
    del latest_core_count, latest_headlines  # v2 히어로는 상태 문구만 표시 (§4-7)

    dates = sorted(
        (p.stem for p in dashboard_dir.glob("*.html") if p.stem not in ("index", "archive")),
        reverse=True,
    )

    status = run_status.load_status(state_path)
    if status is None:
        status_text = "실행 이력 없음"
        status_class = ""
    elif status.get("last_run_status") == "success":
        status_text = f'● 정상 · 마지막 성공 {_esc(status.get("last_success_at", "-"))}'
        status_class = "ok"
    else:
        status_text = f'● 실패 · 마지막 성공 {_esc(status.get("last_success_at", "-"))}'
        status_class = "fail"

    parts = [
        "<!doctype html>",
        '<html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>반도체 뉴스 브리핑</title>",
        '<link rel="stylesheet" href="style.css">',
        "</head><body>",
        _build_appbar(),
        _build_search_bar(),
    ]

    if radar_data:
        parts.append(build_radar_section_html(radar_data))

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

    # 상태 문구는 히어로 배너(있을 때만 존재) 안이 아니라 항상 렌더링한다 — 아직 브리핑이
    # 하나도 없어도(예: 첫 실행이 실패해 대시보드 파일 자체가 안 생긴 경우) "침묵 실패"
    # 없이 실패 사실이 보여야 한다.
    parts.append(f'<p class="status {status_class}">{status_text}</p>')

    if not dates:
        parts.append('<p class="summary">아직 생성된 브리핑이 없습니다.</p>')
    else:
        latest = dates[0]
        parts.append(f'<a class="hero" href="{_esc(latest)}.html"><h2>🔍 오늘의 데일리 리포트</h2></a>')

        trend_articles = _load_latest_trend_articles(dashboard_dir, latest, issues_path)
        trends = _compute_keyword_trends(trend_articles)
        parts.append(render_trend_section(trends, sum(t["count"] for t in trends)))

        parts.append('<div id="feed">')
        for d in dates:
            parts.append(_build_report_card(dashboard_dir, d))
        parts.append("</div>")

    parts.append('<p class="row"><a href="archive.html">지난 리포트 전체보기 &rarr;</a></p>')

    parts.append(_SITE_FOOTER)
    parts.append(_DASHBOARD_SCRIPT)
    parts.append("</body></html>")
    return "\n".join(parts)


_DASHBOARD_CSS = """\
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css");
:root{
  --paper:#F5F6F8; --surface:#FFF; --ink:#1A1D24; --ink-soft:#8A909C; --line:#ECEEF2;
  --brand:#6C5CE7; --brand-2:#8E7DF5; --action:#3D6FE6; --pill-active:#14161B;
  --confirmed:#2E9E5B; --observed:#C9821A; --muted:#6B7280; --warn-bg:#FFF6E5; --warn-line:#F0C36D;
  --font-sans:"Pretendard",-apple-system,"Segoe UI","Apple SD Gothic Neo",sans-serif;
}
*{box-sizing:border-box}
body{font-family:var(--font-sans);max-width:560px;margin:0 auto;padding:16px 16px 56px;
  color:var(--ink);background:var(--paper);line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--action);text-decoration:none}
a:hover{text-decoration:underline}

/* 헤더 */
.appbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.brand{display:inline-block;background:#14161B;color:#fff;font-weight:700;font-size:.85rem;
  padding:4px 10px;border-radius:6px;transform:skew(-6deg)}
.search{display:flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--line);
  border-radius:12px;padding:11px 14px;margin-bottom:16px}
.search input{border:0;outline:0;flex:1;font-family:inherit;font-size:.9rem;background:transparent;color:var(--ink)}
.search input::placeholder{color:var(--ink-soft)}
.search .i{color:var(--action)}

/* 날짜 내비(선택) */
.date-select{font-family:inherit;font-size:.82rem;color:var(--ink);background:var(--surface);
  border:1px solid var(--line);border-radius:8px;padding:4px 8px}

/* pill 필터 */
.filter{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px;margin:0 0 14px}
.filter button{flex:0 0 auto;font-family:inherit;font-size:.85rem;color:var(--ink-soft);
  background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:7px 15px;cursor:pointer}
.filter button[aria-pressed="true"]{background:var(--pill-active);color:#fff;border-color:var(--pill-active)}

/* 상태 문구 (침묵 실패 방지 — 브리핑이 하나도 없을 때도 항상 표시) */
.status{font-size:.8rem;color:var(--ink-soft);margin:0 0 14px}
.status.ok{color:var(--confirmed)}
.status.fail{color:#C23B3B;font-weight:600}

/* 히어로 배너 */
.hero{display:block;background:linear-gradient(100deg,var(--brand-2),var(--brand));color:#fff;
  border-radius:16px;padding:18px 20px;margin:0 0 18px}
.hero h2{margin:0;font-size:1.05rem;font-weight:600;color:#fff;display:flex;align-items:center;gap:8px}

/* 카드 공통 */
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;
  padding:15px 16px;margin:0 0 11px;transition:box-shadow .15s}
.card:hover{box-shadow:0 4px 14px rgba(26,29,36,.06)}
.row{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.spacer{flex:1}
.time{color:var(--ink-soft);font-size:.78rem}
.title{font-size:1rem;font-weight:700;line-height:1.4;margin:.55rem 0;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.summary{font-size:.9rem;color:var(--ink);margin:.35rem 0}
.summary.mut{color:#4B5563;font-style:italic}
.cardfoot{display:flex;align-items:center;justify-content:space-between;margin-top:.5rem}
.cardfoot a{font-size:.85rem}

/* 오늘의 핵심 하이라이트 */
.highlight-strip{display:flex;gap:10px;overflow-x:auto;padding-bottom:6px;margin:0 0 14px;scroll-snap-type:x proximity}
.highlight-card{flex:0 0 220px;scroll-snap-align:start;background:var(--surface);
  border:1px solid var(--line);border-left:3px solid var(--brand);border-radius:14px;padding:13px 14px}
.highlight-card .title{font-size:.92rem;margin:.5rem 0;-webkit-line-clamp:2}
.highlight-card .summary{font-size:.82rem;margin:.3rem 0;
  display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}

/* 배지·칩 */
.badge{font-size:.74rem;font-weight:600;padding:3px 9px;border-radius:999px;background:#EEF0F3;color:#5A6472}
.badge.s-samsung{background:#ECEBFB;color:#5B4FC4}
.badge.s-hynix{background:#E4F0FB;color:#2C6BB5}
.badge.s-thelec{background:#E1F1EF;color:#1F7A6B}
.badge.s-eetimes{background:#FDE9DD;color:#C2652A}
.badge.s-digitimes{background:#FDF1D6;color:#A9790B}
.badge.s-semieng{background:#E7F2E6;color:#3B8B4E}
.chip{font-size:.74rem;color:var(--ink-soft);padding:3px 9px;border:1px solid var(--line);border-radius:999px}
.chip.stock-up{background:rgba(46,158,91,.12);color:var(--confirmed);border-color:transparent}
.chip.stock-down{background:rgba(194,59,59,.1);color:#C23B3B;border-color:transparent}
.chip.warn-chip{background:var(--warn-bg);border:1px solid var(--warn-line);color:#A9790B}

/* 확정/관측/요약없음 상태 배지 — 아이콘 + 색상 (카테고리 태그와 시각적으로 구분) */
.badge-confirm{display:inline-flex;align-items:center;gap:3px;font-size:.74rem;font-weight:600;
  padding:3px 9px;border-radius:999px}
.badge-confirm.ok{background:#E3F6EA;color:#1B7A45}
.badge-confirm.obs{background:#FBEFDD;color:#8A5A10}
.badge-confirm.mut{background:#EEF0F3;color:#4B5563}

/* 카테고리 배지 — 알약 모양 윤곽선 (확정/관측 배지와 구분) */
.badge-category{font-size:.74rem;color:#5D6470;padding:3px 9px;border:1px solid var(--line);border-radius:999px}

/* 리포트 카드(인덱스) */
.report .datetitle{font-size:1.05rem;font-weight:700;margin:.5rem 0 .6rem}
.report .actions{display:flex;gap:18px}
.report .actions a{display:inline-flex;align-items:center;gap:6px;font-size:.9rem}

/* 확인 필요(접이식 — .card 재사용) */
.pending-list{margin:.6rem 0 0;padding-left:1.1rem}
.pending-list li{margin-bottom:.4rem;font-size:.92rem}

/* 표 */
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.85rem;background:var(--surface);border-radius:12px;overflow:hidden}
th,td{border-bottom:1px solid var(--line);padding:9px 11px;text-align:left}
th{background:#F1F3F6;font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr.warn td{background:var(--warn-bg)}

/* 섹션 제목·푸터 */
h2.sec{font-size:1.05rem;font-weight:700;margin:1.6rem 0 .7rem}
.alert-banner{background:#FDECEC;border:1px solid #F3B4B4;border-radius:14px;padding:12px 16px;margin:0 0 14px}
.site-footer{margin-top:2.4rem;padding-top:1rem;border-top:1px solid var(--line);font-size:.76rem;color:var(--ink-soft)}
:focus-visible{outline:2px solid var(--action);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}

/* 경쟁 구도 레이더 */
.radar-bars{margin:.4rem 0 1rem}
.radar-row{display:flex;align-items:center;gap:8px;margin:.3rem 0}
.radar-label{width:100px;font-size:.82rem;color:var(--ink-soft)}
.radar-bar{display:block;height:.85rem;background:var(--brand);border-radius:3px}
.radar-count{font-size:.8rem;color:var(--ink-soft)}

/* R&D·특허 소스 배지, 노이즈 신고 */
.badge-type{background:#EEF0F3;color:var(--ink-soft)}
.filter-toggle{display:inline-block;margin:0 0 10px;font-size:.85rem;color:var(--ink-soft)}
.noise-btn{font:inherit;font-size:.76rem;color:#A94442;text-decoration:none;background:transparent;
  border:1px solid #A94442;border-radius:6px;padding:2px 8px;cursor:pointer}
.toast{font-size:.76rem;color:var(--confirmed);margin-left:6px}

/* 실시간 트렌드 */
.trend{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:16px;margin:0 0 18px}
.trend-head{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:6px}
.trend .sub{font-size:.78rem;color:var(--ink-soft)}
.trend-body{display:flex;gap:18px;align-items:center}
.trend-donut{flex:0 0 160px;display:flex;justify-content:center}
.trend-bars{flex:1;min-width:0}
.donut-num{font-size:20px;font-weight:700;fill:var(--ink)}
.donut-cap{font-size:10px;fill:var(--ink-soft)}
.tbar{display:flex;align-items:center;gap:8px;margin:7px 0}
.tbar .k{flex:0 0 84px;font-size:.82rem;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tbar .track{flex:1;height:10px;background:#EEF0F3;border-radius:999px;overflow:hidden}
.tbar .fill{display:block;height:100%;border-radius:999px}
.tbar .p{flex:0 0 42px;text-align:right;font-size:.8rem;color:var(--ink-soft);font-variant-numeric:tabular-nums}
@media(max-width:480px){.trend-body{flex-direction:column;align-items:stretch}.trend-donut{align-self:center}}
"""

_MAX_ACTIVE_ISSUES = 5


def _rank_active_issues(issues: list[dict]) -> list[dict]:
    """진행 중 이슈를 관련 기사 수(반복 보도 정도) 내림차순, 최신 갱신일 내림차순으로 정렬해
    상위 _MAX_ACTIVE_ISSUES개만 남긴다. 기사 1건짜리 단발성 이슈보다 반복 보도된 이슈를
    우선 노출해 "진짜 중요한" 이슈만 대시보드에 보이게 한다.
    """
    ranked = sorted(
        issues,
        key=lambda i: (len(i.get("related_article_ids") or []), i.get("last_updated", "")),
        reverse=True,
    )
    return ranked[:_MAX_ACTIVE_ISSUES]


def run(
    summarized_articles: list[dict],
    pending_review_articles: list[dict],
    collection_stats: dict,
    archive_path: str,
    dashboard_dir: str,
    today: str,
    state_path: str,
    issues_path: str | None = None,
    radar_data: dict | None = None,
    mention_trend_data: dict | None = None,
    cold_start_stage: str = "active",
) -> str:
    """Step 5 진입점. 마크다운 아카이브와 HTML 대시보드를 함께 생성한다.

    Args:
        summarized_articles: data/summarized/YYYY-MM-DD.json 로드 결과
        pending_review_articles: data/classified/YYYY-MM-DD.json 중 "확인 필요" tier 기사
        collection_stats: 소스별 수집 통계
        archive_path: data/archive/YYYY-MM-DD.md 저장 경로
        dashboard_dir: data/dashboard 디렉토리 경로
        today: YYYY-MM-DD 형식 날짜 문자열
        state_path: data/state/run_status.json 경로 (index.html 상태 표시용)
        issues_path: data/state/issues.json 경로 (진행 중 이슈 타임라인·속보 배너용, Phase 3, 선택)
        radar_data: 경쟁 구도 레이더 주간 데이터 (Phase 4, 선택). index.html 상단 섹션에 포함된다.
        mention_trend_data: 언급량 트렌드 데이터 (Phase 5, 선택). build_index_html로 그대로 전달된다.
        cold_start_stage: 콜드 스타트 단계 (Phase 5). build_index_html로 그대로 전달된다.

    Returns:
        생성된 브리핑 마크다운 문서 문자열 (archive_path에도 저장)
    """
    active_issues = []
    if issues_path is not None:
        active_issues = _rank_active_issues(
            [
                issue
                for issue in issue_tracking.load_issues(Path(issues_path))
                if issue.get("status") == "진행중"
            ]
        )

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
        all_dates=all_dates,
        active_issues=active_issues,
    )
    (dashboard_dir / f"{today}.html").write_text(dashboard_html, encoding="utf-8")

    # 새 날짜가 추가됐으므로 이전 페이지들의 날짜 드롭다운도 최신 목록으로 갱신한다.
    _refresh_date_selects(dashboard_dir, all_dates)

    (dashboard_dir / "style.css").write_text(_DASHBOARD_CSS, encoding="utf-8")

    index_html = build_index_html(
        dashboard_dir,
        Path(state_path),
        issues_path=Path(issues_path) if issues_path else None,
        radar_data=radar_data,
        mention_trend_data=mention_trend_data,
        cold_start_stage=cold_start_stage,
    )
    (dashboard_dir / "index.html").write_text(index_html, encoding="utf-8")

    archive_html = build_archive_html(dashboard_dir)
    (dashboard_dir / "archive.html").write_text(archive_html, encoding="utf-8")

    return briefing
