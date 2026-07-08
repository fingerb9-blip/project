# 이메일 → GitHub Pages 대시보드 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매일 발송되던 브리핑 이메일(Gmail SMTP)을 GitHub Pages 정적 대시보드로 교체하고, 실패 알림 이메일은 그대로 유지한다.

**Architecture:** Step 5(조립)가 기존 `data/archive/*.md`에 더해 날짜별 카드형 HTML(`data/dashboard/YYYY-MM-DD.html`)과 날짜 목록 인덱스(`data/dashboard/index.html`)를 생성하도록 확장한다. Step 6(발송·저장)은 이메일 발송 대신 대시보드 산출물이 정상 생성됐는지 확인하는 역할로 축소한다. GitHub Actions 워크플로우에 GitHub Pages 배포 스텝을 추가한다.

**Tech Stack:** Python 3.12, pytest(신규 도입), 순수 HTML/CSS(클라이언트 JS 없음), GitHub Actions `actions/upload-pages-artifact` + `actions/deploy-pages`.

## Global Constraints

- 실패 알림 이메일(`src/notify.py`)의 로직·문구는 변경하지 않는다 — 설정 로드 실패, 인증 오류, 파이프라인 실행 실패는 계속 관리자 이메일로 알림
- Step 0~4(설정 로드·수집·중복제거·분류·요약) 로직은 변경하지 않는다
- `data/archive/YYYY-MM-DD.md` 아카이브 생성은 그대로 유지한다
- 대시보드 생성 코드(`build_dashboard_html`, `build_index_html`)는 기사 데이터·통계만 사용하며 환경변수나 Secrets를 절대 참조하지 않는다
- 대시보드는 공개 URL로 배포되므로, RSS/뉴스 소스에서 온 `title`/`summary`/`source`/`url`은 반드시 `html.escape()` 처리하고, `url`은 `http`/`https` 스킴만 허용한다 (XSS 방지)
- 정적 HTML/CSS만 사용한다 — 클라이언트 사이드 JS, 프레임워크, 라우팅 라이브러리 금지
- 테스트는 프로젝트 루트에서 `python -m pytest tests/ -v`로 실행한다 (main.py가 `python main.py`로 루트에서 실행되는 것과 동일한 방식으로 `src` 패키지를 임포트하기 위함)

---

### Task 1: `step0_init.py` — `dashboard_dir` 경로 추가

**Files:**
- Modify: `src/step0_init.py:58-78` (`prepare_today_paths` 함수)
- Test: `tests/test_step0_init.py` (신규)

**Interfaces:**
- Produces: `prepare_today_paths(base_dir, today) -> dict`의 반환값에 `paths["dashboard_dir"]` (Path, `data/dashboard` 디렉토리, 실행 시점에 이미 `mkdir`된 상태) 추가

- [ ] **Step 1: pytest를 requirements.txt에 추가**

`requirements.txt`에 아래 줄 추가:

```
pytest==8.3.4
```

설치:

```bash
pip install -r requirements.txt
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_step0_init.py` 신규 생성:

```python
from src import step0_init


def test_prepare_today_paths_creates_dashboard_dir(tmp_path):
    paths = step0_init.prepare_today_paths(tmp_path, "2026-07-08")

    assert paths["dashboard_dir"] == tmp_path / "data" / "dashboard"
    assert paths["dashboard_dir"].is_dir()
```

- [ ] **Step 3: 테스트 실패 확인**

실행: `python -m pytest tests/test_step0_init.py -v`
예상 결과: `KeyError: 'dashboard_dir'`로 FAIL

- [ ] **Step 4: `prepare_today_paths` 수정**

`src/step0_init.py`의 기존 `prepare_today_paths` 함수를 아래로 교체:

```python
def prepare_today_paths(base_dir: Path, today: str) -> dict:
    """오늘 날짜 기준 data/*/YYYY-MM-DD.json 경로를 생성한다.

    Args:
        base_dir: 프로젝트 루트 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        Step별 출력 경로 dict
    """
    paths = {
        "raw": base_dir / "data" / "raw" / f"{today}.json",
        "dedup": base_dir / "data" / "dedup" / f"{today}.json",
        "classified": base_dir / "data" / "classified" / f"{today}.json",
        "summarized": base_dir / "data" / "summarized" / f"{today}.json",
        "archive": base_dir / "data" / "archive" / f"{today}.md",
        "dashboard_dir": base_dir / "data" / "dashboard",
        "state": base_dir / "data" / "state" / "run_status.json",
    }
    for key, path in paths.items():
        if key == "dashboard_dir":
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
    return paths
```

- [ ] **Step 5: 테스트 통과 확인**

실행: `python -m pytest tests/test_step0_init.py -v`
예상 결과: PASS

- [ ] **Step 6: 커밋**

```bash
git add requirements.txt src/step0_init.py tests/test_step0_init.py
git commit -m "feat: add dashboard_dir to Step 0 output paths"
```

---

### Task 2: `step5_assemble.py` — XSS 안전 헬퍼 + `build_dashboard_html`

**Files:**
- Modify: `src/step5_assemble.py` (상단 import 및 함수 추가)
- Test: `tests/test_step5_assemble.py` (신규)

**Interfaces:**
- Consumes: 없음 (Step 4 출력 스키마만 가정 — `{title, url, source, summary, confirmation_tag, summary_fallback, category}`)
- Produces:
  - `_esc(text) -> str`
  - `_safe_url(url) -> str | None`
  - `build_dashboard_html(summarized_articles: list[dict], pending_review_articles: list[dict], collection_stats: dict, target_date: str) -> str`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_step5_assemble.py` 신규 생성:

```python
from src import step5_assemble


def _sample_article(**overrides):
    article = {
        "title": "삼성전자, 테스트 기사",
        "url": "https://example.com/news/1",
        "source": "테스트소스",
        "summary": "테스트 요약 문장입니다.",
        "confirmation_tag": "[확정]",
        "summary_fallback": False,
        "category": ["메모리"],
    }
    article.update(overrides)
    return article


def test_build_dashboard_html_escapes_article_title():
    malicious = _sample_article(title="<script>alert(1)</script>")
    html_out = step5_assemble.build_dashboard_html([malicious], [], {}, "2026-07-08")
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out


def test_build_dashboard_html_drops_javascript_url():
    malicious = _sample_article(url="javascript:alert(1)")
    html_out = step5_assemble.build_dashboard_html([malicious], [], {}, "2026-07-08")
    assert "javascript:alert(1)" not in html_out


def test_build_dashboard_html_keeps_safe_https_url():
    article = _sample_article(url="https://example.com/article")
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'href="https://example.com/article"' in html_out


def test_build_dashboard_html_includes_summary_and_tag():
    article = _sample_article()
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert "테스트 요약 문장입니다." in html_out
    assert "[확정]" in html_out


def test_build_dashboard_html_renders_category_section():
    article = _sample_article(category=["메모리", "파운드리"])
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert "메모리" in html_out
    assert "파운드리" in html_out


def test_build_dashboard_html_renders_pending_review():
    pending = _sample_article(title="확인 필요 기사")
    html_out = step5_assemble.build_dashboard_html([], [pending], {}, "2026-07-08")
    assert "확인 필요 기사" in html_out


def test_build_dashboard_html_flags_low_collection_count():
    stats = {"디일렉": {"today": 1, "avg7d": 10.0}}
    html_out = step5_assemble.build_dashboard_html([], [], stats, "2026-07-08")
    assert 'class="warn"' in html_out


def test_build_dashboard_html_handles_summary_fallback_article():
    fallback = _sample_article(summary_fallback=True, summary=None, confirmation_tag=None)
    html_out = step5_assemble.build_dashboard_html([fallback], [], {}, "2026-07-08")
    assert "삼성전자, 테스트 기사" in html_out
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `python -m pytest tests/test_step5_assemble.py -v`
예상 결과: `AttributeError: module 'src.step5_assemble' has no attribute 'build_dashboard_html'`로 FAIL

- [ ] **Step 3: 헬퍼 함수 + `build_dashboard_html` 구현**

`src/step5_assemble.py` 상단 import를 아래로 교체:

```python
"""Step 5. 조립 — 브리핑 마크다운 문서 및 대시보드 HTML 생성."""

import html
from pathlib import Path
from urllib.parse import urlparse

from src import run_status

_ALLOWED_URL_SCHEMES = {"http", "https"}
```

`build_briefing` 함수 뒤(기존 `run` 함수 앞)에 아래 함수들 추가:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `python -m pytest tests/test_step5_assemble.py -v`
예상 결과: 8개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/step5_assemble.py tests/test_step5_assemble.py
git commit -m "feat: add XSS-safe dashboard HTML builder to Step 5"
```

---

### Task 3: `step5_assemble.py` — `build_index_html`

**Files:**
- Modify: `src/step5_assemble.py` (함수 추가)
- Test: `tests/test_step5_assemble.py` (테스트 추가)

**Interfaces:**
- Consumes: `run_status.load_status(path) -> dict | None` (기존 `src/run_status.py`)
- Produces: `build_index_html(dashboard_dir: Path, state_path: Path) -> str`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_step5_assemble.py` 파일 끝에 추가:

```python
def test_build_index_html_lists_dates_newest_first(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    for d in ("2026-07-06", "2026-07-08", "2026-07-07"):
        (dashboard_dir / f"{d}.html").write_text("<html></html>", encoding="utf-8")

    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")

    first = html_out.index("2026-07-08")
    second = html_out.index("2026-07-07")
    third = html_out.index("2026-07-06")
    assert first < second < third


def test_build_index_html_shows_success_badge(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text(
        '{"last_run_status": "success", "last_success_at": "2026-07-08T08:12:00+09:00"}',
        encoding="utf-8",
    )

    html_out = step5_assemble.build_index_html(dashboard_dir, state_path)

    assert "badge ok" in html_out
    assert "2026-07-08T08:12:00+09:00" in html_out


def test_build_index_html_shows_failure_badge(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "failed"}', encoding="utf-8")

    html_out = step5_assemble.build_index_html(dashboard_dir, state_path)

    assert "badge fail" in html_out


def test_build_index_html_handles_no_dashboards(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()

    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")

    assert "아직 생성된 브리핑이 없습니다" in html_out
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `python -m pytest tests/test_step5_assemble.py -v`
예상 결과: 새로 추가한 4개 테스트가 `AttributeError: ... has no attribute 'build_index_html'`로 FAIL

- [ ] **Step 3: `build_index_html` 구현**

`src/step5_assemble.py`의 `build_dashboard_html` 함수 뒤에 추가:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `python -m pytest tests/test_step5_assemble.py -v`
예상 결과: 12개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/step5_assemble.py tests/test_step5_assemble.py
git commit -m "feat: add dashboard index page builder to Step 5"
```

---

### Task 4: `step5_assemble.run()` — 대시보드 생성 배선 + 스타일시트

**Files:**
- Modify: `src/step5_assemble.py:65-88` (`run` 함수 전체 교체)
- Test: `tests/test_step5_assemble.py` (테스트 추가)

**Interfaces:**
- Consumes: `build_briefing`, `build_dashboard_html`, `build_index_html` (Task 2, 3에서 정의)
- Produces: `run(summarized_articles, pending_review_articles, collection_stats, archive_path, dashboard_dir, today, state_path) -> str` — 기존 시그니처에 `dashboard_dir: str`, `today: str`, `state_path: str` 파라미터 추가 (순서 주의, main.py에서 이 순서로 호출)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_step5_assemble.py` 파일 끝에 추가:

```python
def test_run_writes_archive_dashboard_and_index(tmp_path):
    archive_path = tmp_path / "archive" / "2026-07-08.md"
    dashboard_dir = tmp_path / "dashboard"
    state_path = tmp_path / "run_status.json"
    state_path.write_text('{"last_run_status": "success"}', encoding="utf-8")

    step5_assemble.run(
        [_sample_article()],
        [],
        {},
        str(archive_path),
        str(dashboard_dir),
        "2026-07-08",
        str(state_path),
    )

    assert archive_path.exists()
    assert (dashboard_dir / "2026-07-08.html").exists()
    assert (dashboard_dir / "index.html").exists()
    assert (dashboard_dir / "style.css").exists()
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `python -m pytest tests/test_step5_assemble.py::test_run_writes_archive_dashboard_and_index -v`
예상 결과: `TypeError: run() takes ... positional arguments but 7 were given`로 FAIL

- [ ] **Step 3: `run` 함수 교체**

`src/step5_assemble.py`의 기존 `run` 함수를 아래로 교체:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `python -m pytest tests/test_step5_assemble.py -v`
예상 결과: 13개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/step5_assemble.py tests/test_step5_assemble.py
git commit -m "feat: wire dashboard HTML generation into Step 5 run()"
```

---

### Task 5: `step6_send.py` — 이메일 발송 → 대시보드 확인으로 축소

**Files:**
- Modify: `src/step6_send.py` (전체 교체)
- Test: `tests/test_step6_send.py` (신규)

**Interfaces:**
- Consumes: `notify.notify_failure(subject, message)` (기존 `src/notify.py`, 변경 없음)
- Produces: `run(dashboard_dir: str, today: str) -> bool` — 기존 `run(briefing_path, smtp_config)` 시그니처를 대체

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_step6_send.py` 신규 생성:

```python
from unittest.mock import patch

from src import step6_send


def test_run_returns_true_when_dashboard_files_exist(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")
    (dashboard_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    assert step6_send.run(str(dashboard_dir), "2026-07-08") is True


@patch("src.step6_send.notify.notify_failure")
def test_run_notifies_and_returns_false_when_daily_html_missing(mock_notify, tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    result = step6_send.run(str(dashboard_dir), "2026-07-08")

    assert result is False
    mock_notify.assert_called_once()
    assert "08:30까지 대시보드 미갱신" in mock_notify.call_args[0][0]


@patch("src.step6_send.notify.notify_failure")
def test_run_notifies_and_returns_false_when_index_missing(mock_notify, tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")

    result = step6_send.run(str(dashboard_dir), "2026-07-08")

    assert result is False
    mock_notify.assert_called_once()
```

- [ ] **Step 2: 테스트 실패 확인**

실행: `python -m pytest tests/test_step6_send.py -v`
예상 결과: `TypeError: run() missing 1 required positional argument` 등으로 FAIL

- [ ] **Step 3: `step6_send.py` 전체 교체**

`src/step6_send.py` 전체 내용을 아래로 교체:

```python
"""Step 6. 저장 확인 — 대시보드 산출물이 정상 생성됐는지 확인한다."""

import logging
from pathlib import Path

from src import notify

logger = logging.getLogger(__name__)


def run(dashboard_dir: str, today: str) -> bool:
    """Step 6 진입점. 08:30까지 대시보드가 갱신되지 않으면 실패 알림을 발송한다
    ("뉴스 없는 날"과 구분).

    Args:
        dashboard_dir: data/dashboard 디렉토리 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        대시보드 산출물 정상 생성 여부 (호출자가 run_status.json에 실제 결과를 반영할 수 있도록)
    """
    dashboard_dir = Path(dashboard_dir)
    daily_html = dashboard_dir / f"{today}.html"
    index_html = dashboard_dir / "index.html"

    missing = [p for p in (daily_html, index_html) if not p.exists()]
    if missing:
        notify.notify_failure(
            "08:30까지 대시보드 미갱신",
            f"대시보드 파일이 생성되지 않았습니다: {', '.join(str(p) for p in missing)}",
        )
        return False

    return True
```

- [ ] **Step 4: 테스트 통과 확인**

실행: `python -m pytest tests/test_step6_send.py -v`
예상 결과: 3개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/step6_send.py tests/test_step6_send.py
git commit -m "feat: replace Step 6 email send with dashboard verification"
```

---

### Task 6: `main.py` — Step 5/6 호출부 배선 변경

**Files:**
- Modify: `main.py:81-100` (Step 4 이후 ~ Step 6 호출부)

**Interfaces:**
- Consumes: `step5_assemble.run(...)` (Task 4의 새 시그니처), `step6_send.run(dashboard_dir, today)` (Task 5의 새 시그니처), `paths["dashboard_dir"]` (Task 1)

- [ ] **Step 1: `main.py`의 Step 5~6 블록 교체**

`main.py`에서 아래 블록:

```python
        pending_review = [a for a in classified_articles if a.get("tier") == "확인 필요"]
        collection_stats = _compute_collection_stats(base_dir, config["feeds"], raw_articles, today)
        step5_assemble.run(summarized_articles, pending_review, collection_stats, paths["archive"])
        steps_completed.append("assemble")

        smtp_config = {
            "host": os.environ["SMTP_HOST"],
            "port": os.environ["SMTP_PORT"],
            "user": os.environ["SMTP_USER"],
            "password": os.environ["SMTP_PASSWORD"],
            "to": os.environ["SMTP_TO"],
        }
        if not step6_send.run(paths["archive"], smtp_config):
            raise RuntimeError("Step 6 발송 실패 (08:30 발송 미완료)")
        steps_completed.append("send")
```

을 아래로 교체:

```python
        pending_review = [a for a in classified_articles if a.get("tier") == "확인 필요"]
        collection_stats = _compute_collection_stats(base_dir, config["feeds"], raw_articles, today)
        step5_assemble.run(
            summarized_articles,
            pending_review,
            collection_stats,
            paths["archive"],
            paths["dashboard_dir"],
            today,
            paths["state"],
        )
        steps_completed.append("assemble")

        if not step6_send.run(paths["dashboard_dir"], today):
            raise RuntimeError("Step 6 검증 실패 (08:30까지 대시보드 미갱신)")
        steps_completed.append("send")
```

위 SMTP 블록이 `main.py` 안에서 `os.environ`의 유일한 사용처였으므로, 파일 상단의 `import os` 줄(다른 import들과 함께 있는 줄)을 삭제한다. `main.py`에 남아있는 `os.environ["GEMINI_API_KEY"]` 등은 `src/gemini_client.py` 내부에서 별도로 처리하므로 `main.py`에는 영향이 없다.

- [ ] **Step 2: 로컬 스모크 테스트로 배선 확인**

`main.py`는 Gemini API 키와 실제 RSS 피드 접근이 필요해 전체를 자동 테스트하기 어렵다. 대신 배선만 빠르게 확인한다:

```bash
python -c "
import ast
with open('main.py', encoding='utf-8') as f:
    ast.parse(f.read())
print('main.py syntax OK')
"
```

예상 결과: `main.py syntax OK` 출력 (문법 오류 없음 확인)

- [ ] **Step 3: 기존 단위 테스트 전체 재실행 (회귀 확인)**

```bash
python -m pytest tests/ -v
```

예상 결과: Task 1~5에서 작성한 모든 테스트 PASS (main.py는 단위 테스트 대상이 아니므로 이 스텝은 회귀만 확인)

- [ ] **Step 4: 커밋**

```bash
git add main.py
git commit -m "feat: wire main.py to dashboard-based Step 5/6"
```

---

### Task 7: GitHub Actions — Pages 배포 스텝 추가

**Files:**
- Modify: `.github/workflows/daily_briefing.yml`

**Interfaces:**
- 없음 (CI 설정 변경, 코드 인터페이스 없음)

- [ ] **Step 1: `permissions` 블록에 Pages 권한 추가**

`.github/workflows/daily_briefing.yml`의 기존:

```yaml
permissions:
  contents: write
```

을 아래로 교체:

```yaml
permissions:
  contents: write
  pages: write
  id-token: write
```

- [ ] **Step 2: `jobs.run`에 `environment` 블록 추가**

기존:

```yaml
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 20
```

을 아래로 교체:

```yaml
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
```

- [ ] **Step 3: `Commit state & archive` 스텝에 `data/dashboard` 추가하고, 배포 스텝 추가**

기존:

```yaml
      - name: Commit state & archive
        if: success()
        run: |
          git config user.name "briefing-bot"
          git config user.email "bot@users.noreply.github.com"
          git add data/archive data/state
          git commit -m "chore: daily run $(date +%F)" || echo "no changes"
          git push

      - name: Notify on failure
```

을 아래로 교체:

```yaml
      - name: Commit state & archive
        if: success()
        run: |
          git config user.name "briefing-bot"
          git config user.email "bot@users.noreply.github.com"
          git add data/archive data/state data/dashboard
          git commit -m "chore: daily run $(date +%F)" || echo "no changes"
          git push

      - name: Upload dashboard artifact
        if: success()
        uses: actions/upload-pages-artifact@v3
        with:
          path: data/dashboard

      - name: Deploy to GitHub Pages
        if: success()
        id: deployment
        uses: actions/deploy-pages@v4

      - name: Notify on failure
```

- [ ] **Step 4: YAML 문법 검증**

```bash
python -c "
import yaml
with open('.github/workflows/daily_briefing.yml', encoding='utf-8') as f:
    yaml.safe_load(f)
print('workflow YAML OK')
"
```

예상 결과: `workflow YAML OK` 출력

- [ ] **Step 5: 커밋**

```bash
git add .github/workflows/daily_briefing.yml
git commit -m "ci: deploy dashboard to GitHub Pages after daily run"
```

- [ ] **Step 6: (사용자 직접 수행) Pages 활성화**

GitHub 리포지토리 Settings → Pages → Build and deployment → Source를 **"GitHub Actions"** 로 변경한다. 이 설정은 웹 UI에서만 가능하므로 사용자가 직접 수행해야 한다. 이후 `workflow_dispatch`로 수동 실행하면 Actions 탭의 "Deploy to GitHub Pages" 스텝 로그에 배포된 URL이 출력된다.

---

### Task 8: 기존 2026-07-08 아카이브 데이터로 대시보드 백필

**Files:**
- 생성(코드 아님, 데이터 산출물): `data/dashboard/2026-07-08.html`, `data/dashboard/index.html`, `data/dashboard/style.css`

**Interfaces:**
- Consumes: Task 4의 `step5_assemble.run(...)`, `main._compute_collection_stats(base_dir, feeds_config, raw_articles, today)` (기존 `main.py` 함수, 변경 없음)

이 프로젝트는 이미 2026-07-08 하루치 데이터(`data/summarized`, `data/classified`, `data/raw`)가 있다. 이 데이터로 대시보드를 미리 생성해두지 않으면, Pages를 처음 활성화했을 때 `index.html`에 목록이 비어 있게 된다.

- [ ] **Step 1: 기존 데이터로 대시보드 생성**

프로젝트 루트에서 실행:

```bash
python -c "
import json
from pathlib import Path

import yaml

import main as main_module
from src import step5_assemble

base_dir = Path('.').resolve()
today = '2026-07-08'

with open('data/summarized/2026-07-08.json', encoding='utf-8') as f:
    summarized = json.load(f)
with open('data/classified/2026-07-08.json', encoding='utf-8') as f:
    classified = json.load(f)
with open('data/raw/2026-07-08.json', encoding='utf-8') as f:
    raw = json.load(f)
with open('sources/feeds.yaml', encoding='utf-8') as f:
    feeds = yaml.safe_load(f)

pending = [a for a in classified if a.get('tier') == '확인 필요']
stats = main_module._compute_collection_stats(base_dir, feeds, raw, today)

step5_assemble.run(
    summarized, pending, stats,
    'data/archive/2026-07-08.md', 'data/dashboard', today, 'data/state/run_status.json',
)
print('backfill done')
"
```

예상 결과: `backfill done` 출력, `data/archive/2026-07-08.md` 내용은 기존과 동일하게 재생성됨(덮어쓰기)

- [ ] **Step 2: 산출물 확인**

```bash
ls data/dashboard/
```

예상 결과: `2026-07-08.html`, `index.html`, `style.css` 3개 파일 존재

브라우저에서 `data/dashboard/index.html`을 직접 열어 "최신 브리핑 보기 (2026-07-08)" 링크와 상태 배지가 보이는지, 클릭 시 `2026-07-08.html`에서 4개 섹션(오늘의 핵심/카테고리별/확인 필요/수집 상태)이 정상 렌더링되는지 확인한다.

- [ ] **Step 3: 커밋**

```bash
git add data/dashboard data/archive/2026-07-08.md
git commit -m "chore: backfill dashboard for 2026-07-08"
```

---

### Task 9: 문서 갱신 — `CLAUDE.md`, `docs/phase1_ipo.md`

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/phase1_ipo.md`

**Interfaces:**
- 없음 (문서 변경)

- [ ] **Step 1: `CLAUDE.md`의 "전달 채널" 항목 수정**

`CLAUDE.md`에서:

```
| 전달 채널 | Gmail SMTP (앱 비밀번호, 무료) |
```

을 아래로 교체:

```
| 전달 채널 | GitHub Pages 대시보드 (브리핑 본문) + Gmail SMTP (앱 비밀번호, 실패 알림 전용) |
```

- [ ] **Step 2: `docs/phase1_ipo.md`의 Step 5/6 설명 수정**

`docs/phase1_ipo.md`에서 Step 5 섹션:

```
### Step 5. 조립 (`step5_assemble.py`)

- **Input**: Step 4 결과, 브리핑 템플릿
- **Process**: ①오늘의 핵심 ②카테고리별 ③확인 필요 목록 ④수집 상태(소스별 건수 vs 최근 7일 평균) 순으로 마크다운/HTML 브리핑 문서 생성
- **Output**: `data/archive/YYYY-MM-DD.md`
```

을 아래로 교체:

```
### Step 5. 조립 (`step5_assemble.py`)

- **Input**: Step 4 결과, 브리핑 템플릿
- **Process**: ①오늘의 핵심 ②카테고리별 ③확인 필요 목록 ④수집 상태(소스별 건수 vs 최근 7일 평균) 순으로 마크다운 아카이브 문서와 HTML 대시보드 페이지를 함께 생성. 대시보드 생성 코드는 기사 데이터·통계만 사용하며 환경변수/Secrets를 참조하지 않고, 외부 소스 텍스트는 모두 이스케이프 처리(XSS 방지)
- **Output**: `data/archive/YYYY-MM-DD.md` (아카이브), `data/dashboard/YYYY-MM-DD.html` (해당 날짜 대시보드), `data/dashboard/index.html` (날짜별 목록 + 최근 실행 상태 배지)
```

`docs/phase1_ipo.md`에서 Step 6 섹션:

```
### Step 6. 발송·저장 (`step6_send.py`)

- **Input**: Step 5 결과
- **Process**: Gmail SMTP로 08:30 발송, 아카이브 저장, 실행 로그 기록
- **Output**: 발송 완료 로그
- **실패 처리**: 08:30까지 미완료 시 실패 알림 발송("뉴스 없는 날"과 구분되는 별도 알림)
```

을 아래로 교체:

```
### Step 6. 저장 확인 (`step6_send.py`)

- **Input**: Step 5 결과 (`data/dashboard/` 산출물)
- **Process**: 대시보드 HTML(`YYYY-MM-DD.html`, `index.html`)이 정상 생성됐는지 확인. GitHub Actions 워크플로우가 이 산출물을 GitHub Pages에 배포
- **Output**: 저장 확인 완료 로그. 브리핑 "본문"은 더 이상 이메일로 발송하지 않고 GitHub Pages 대시보드에서 확인
- **실패 처리**: 08:30까지 대시보드가 갱신되지 않으면 관리자 이메일로 실패 알림 발송("뉴스 없는 날"과 구분되는 별도 알림) — 이 알림 자체는 Gmail SMTP를 계속 사용
```

- [ ] **Step 3: 커밋**

```bash
git add CLAUDE.md docs/phase1_ipo.md
git commit -m "docs: update Step 5/6 spec for dashboard delivery"
```
