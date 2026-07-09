# 대시보드 "지난 리포트 전체보기" 아카이브 페이지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `data/dashboard/`에 이미 쌓인 날짜별 리포트(`YYYY-MM-DD.html`)를 월별로 그룹핑해 보여주는 `build_archive_html()`을 추가하고, `data/dashboard/archive.html`로 출력한다. `build_index_html()`에서 이 페이지로 가는 링크를 추가하고, `step5_assemble.run()` 안에서 자동 생성되게 한다.

**Architecture:** `build_archive_html()`은 `build_index_html()`이 이미 하는 것과 동일한 방식(`dashboard_dir.glob("*.html")` 스캔)으로 날짜 목록을 얻지만, 평평한 목록이 아니라 `YYYY-MM` 기준으로 그룹핑한다. 기존 `_build_report_card()`(리포트 카드 렌더링)를 그대로 재사용해 목록 UI를 통일한다.

**Tech Stack:** Python 3.10+, pytest (기존 `tests/test_step5_assemble.py` 패턴과 동일)

## Global Constraints

- `build_index_html()`, `run()`의 기존 파라미터 시그니처는 바꾸지 않는다.
- 디자인은 `src/step5_assemble.py`의 `build_dashboard_html()`, `build_index_html()`, `_DASHBOARD_CSS` 세 곳에서만 산다(파일 상단 docstring) — `build_archive_html()`은 이 원칙의 예외로 신설하는 네 번째 지점이 되므로, 파일 상단 docstring도 함께 갱신한다.
- 외부에서 온 문자열(파일명에서 유도된 날짜 등)은 `_esc()`를 통과시킨다.
- 테스트는 `python -m pytest tests/test_step5_assemble.py -v` 로 실행한다 (프로젝트 루트에서).

## 사전 조사 결과 (구현 전 확인 필요 사항에 대한 답)

**Q1. `build_archive_html()`이 어떤 데이터를 기준으로 그룹핑하는가?**
`build_index_html()`(`src/step5_assemble.py:986-989`)과 완전히 같은 방식이다 — 별도 인덱스 파일이나 DB 없이, `dashboard_dir.glob("*.html")`로 실제 존재하는 파일명(`YYYY-MM-DD.html`)을 스캔해 `.stem`(파일명에서 확장자 제거)을 날짜 문자열로 쓴다. `index`/`archive` 자기 자신은 제외한다. 그룹 키는 날짜 문자열의 앞 7글자(`YYYY-MM`)이다. 새 데이터 소스나 스키마는 필요 없다 — 이미 있는 파일 목록을 다르게 렌더링하는 것뿐이다.

**Q2. `main.py`를 직접 수정해야 하는가?**
아니다. 요청하신 대로 `archive.html` 생성을 `step5_assemble.run()` 안에 넣으면, `main.py`는 이미 `run()`을 호출하고 있으므로(`main.py:125`) 파이프라인에 자동으로 편입된다. `main.py` 자체는 수정하지 않는다.

**Q3. GitHub Actions가 `archive.html`을 자동으로 배포하는가?**
확인 결과 이미 그렇다 — `.github/workflows/daily_briefing.yml:57`의 `git add data/archive data/state data/dashboard`가 `data/dashboard/` 전체를 커밋하고, `:67`의 `actions/upload-pages-artifact@v3`도 `path: data/dashboard`로 그 디렉토리 전체를 통째로 Pages 아티팩트로 올린다. 파일 단위 allowlist가 없어서, `run()`이 `archive.html`을 그 안에 써넣기만 하면 다른 파일(예: `style.css`)과 동일하게 자동 커밋·배포된다. **워크플로우 파일 수정은 필요 없다.**

---

## Task 1: `build_archive_html()` 추가 + `build_index_html()` 링크 + `run()` 연결

**Files:**
- Modify: `src/step5_assemble.py`
- Test: `tests/test_step5_assemble.py`

**Interfaces:**
- Produces: `step5_assemble.build_archive_html(dashboard_dir: Path) -> str`, `step5_assemble._korean_month_title(yyyymm: str) -> str`
- Consumes (기존): `_build_report_card(dashboard_dir, iso_date)`, `_build_appbar()`, `_esc()`, `_SITE_FOOTER`

- [ ] **Step 1: `build_archive_html()`이 월별로 그룹핑하는지 — 실패하는 테스트부터**

`tests/test_step5_assemble.py`에 추가 (파일 하단):

```python
def test_build_archive_html_groups_reports_by_month(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    for d in ["2026-06-30", "2026-07-01", "2026-07-08"]:
        (dashboard_dir / f"{d}.html").write_text("<html></html>", encoding="utf-8")

    html_out = step5_assemble.build_archive_html(dashboard_dir)

    assert "2026년 7월" in html_out
    assert "2026년 6월" in html_out
    assert html_out.index("2026년 7월") < html_out.index("2026년 6월")  # 최신 월 먼저


def test_build_archive_html_lists_dates_within_month_descending(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    for d in ["2026-07-01", "2026-07-08"]:
        (dashboard_dir / f"{d}.html").write_text("<html></html>", encoding="utf-8")

    html_out = step5_assemble.build_archive_html(dashboard_dir)

    assert html_out.index('href="2026-07-08.html"') < html_out.index('href="2026-07-01.html"')


def test_build_archive_html_excludes_index_and_itself(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")
    (dashboard_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    (dashboard_dir / "archive.html").write_text("<html></html>", encoding="utf-8")

    html_out = step5_assemble.build_archive_html(dashboard_dir)

    assert 'href="index.html.html"' not in html_out
    assert 'href="archive.html.html"' not in html_out
    assert 'href="2026-07-08.html"' in html_out


def test_build_archive_html_handles_empty_dashboard_dir(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()

    html_out = step5_assemble.build_archive_html(dashboard_dir)

    assert "아직 생성된 브리핑이 없습니다" in html_out


def test_build_archive_html_includes_working_search(tmp_path):
    """검색창은 index.html과 동일한 _DASHBOARD_SCRIPT를 재사용해 동작한다 — 이 스크립트는
    #feed .card를 대상으로 검색하므로, 카드들이 반드시 하나의 id="feed" 컨테이너 안에
    있어야 한다. .filter/#deep-tech-filter처럼 이 페이지에 없는 요소는 스크립트의
    ||{} 폴백으로 안전하게 무시된다(index.html에서 이미 검증된 패턴)."""
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")

    html_out = step5_assemble.build_archive_html(dashboard_dir)

    assert 'id="q"' in html_out
    assert "#feed .card" in html_out


def test_build_archive_html_wraps_report_cards_in_feed_container(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-08.html").write_text("<html></html>", encoding="utf-8")

    html_out = step5_assemble.build_archive_html(dashboard_dir)

    feed_start = html_out.index('id="feed"')
    card_pos = html_out.index('href="2026-07-08.html"')
    assert feed_start < card_pos
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k build_archive_html -v`
Expected: 6개 모두 `AttributeError: module 'src.step5_assemble' has no attribute 'build_archive_html'`로 FAIL

- [ ] **Step 3: `_korean_month_title()`, `build_archive_html()` 구현**

`src/step5_assemble.py`의 `_korean_date_title()` 함수(현재 위치, `_korean_weekday()` 바로 다음) 뒤에 추가:

```python
def _korean_month_title(yyyymm: str) -> str:
    """'YYYY-MM' 문자열을 아카이브 월별 그룹 제목 'YYYY년 M월'로 변환한다."""
    year, month = yyyymm.split("-")
    return f"{year}년 {int(month)}월"
```

`_build_report_card()` 함수(현재 위치) 바로 다음에 추가:

```python
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
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k build_archive_html -v`
Expected: 6개 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/step5_assemble.py tests/test_step5_assemble.py
git commit -m "feat: add build_archive_html() for monthly-grouped report archive page"
```

---

- [ ] **Step 6: `build_index_html()`에 "지난 리포트 전체보기" 링크 — 실패하는 테스트부터**

`tests/test_step5_assemble.py`에 추가:

```python
def test_build_index_html_includes_archive_link(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()

    html_out = step5_assemble.build_index_html(dashboard_dir, tmp_path / "run_status.json")

    assert 'href="archive.html"' in html_out
```

- [ ] **Step 7: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k includes_archive_link -v`
Expected: FAIL (`archive.html` 링크 없음)

- [ ] **Step 8: `build_index_html()`에 링크 추가**

`src/step5_assemble.py`의 `build_index_html()` 함수 안, 다음 부분:

```python
        parts.append('<div id="feed">')
        for d in dates:
            parts.append(_build_report_card(dashboard_dir, d))
        parts.append("</div>")

    parts.append(_SITE_FOOTER)
```

을 다음으로 교체 (`if not dates: ... else: ...` 블록이 끝난 뒤, 있든 없든 항상 링크를 보여준다):

```python
        parts.append('<div id="feed">')
        for d in dates:
            parts.append(_build_report_card(dashboard_dir, d))
        parts.append("</div>")

    parts.append('<p class="row"><a href="archive.html">지난 리포트 전체보기 &rarr;</a></p>')

    parts.append(_SITE_FOOTER)
```

- [ ] **Step 9: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k includes_archive_link -v`
Expected: PASS

- [ ] **Step 10: 커밋**

```bash
git add src/step5_assemble.py tests/test_step5_assemble.py
git commit -m "feat: link to archive.html from index.html"
```

---

- [ ] **Step 11: `run()`이 `archive.html`도 함께 쓰는지 — 실패하는 테스트부터**

`tests/test_step5_assemble.py`에 추가:

```python
def test_run_writes_archive_html(tmp_path):
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

    archive_html_path = dashboard_dir / "archive.html"
    assert archive_html_path.exists()
    assert "2026년 7월" in archive_html_path.read_text(encoding="utf-8")
```

- [ ] **Step 12: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k test_run_writes_archive_html -v`
Expected: FAIL (`archive.html` 파일 없음)

- [ ] **Step 13: `run()`에 `archive.html` 생성 연결**

`src/step5_assemble.py`의 `run()` 함수 안, 다음 부분:

```python
    index_html = build_index_html(
        dashboard_dir,
        Path(state_path),
        issues_path=Path(issues_path) if issues_path else None,
        radar_data=radar_data,
    )
    (dashboard_dir / "index.html").write_text(index_html, encoding="utf-8")

    return briefing
```

을 다음으로 교체:

```python
    index_html = build_index_html(
        dashboard_dir,
        Path(state_path),
        issues_path=Path(issues_path) if issues_path else None,
        radar_data=radar_data,
    )
    (dashboard_dir / "index.html").write_text(index_html, encoding="utf-8")

    archive_html = build_archive_html(dashboard_dir)
    (dashboard_dir / "archive.html").write_text(archive_html, encoding="utf-8")

    return briefing
```

- [ ] **Step 14: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k test_run_writes_archive_html -v`
Expected: PASS

- [ ] **Step 15: 파일 상단 docstring 갱신**

`src/step5_assemble.py`의 파일 최상단 docstring:

```python
"""Step 5. 조립 — 브리핑 마크다운 문서 및 대시보드 HTML 생성.

HTML/CSS 디자인은 대시보드_디자인_개편_명세_v2_SAVE스타일.md(§3 토큰, §9 CSS)를 따른다.
디자인은 오직 세 곳에서만 산다: build_dashboard_html(), build_index_html(), _DASHBOARD_CSS.
조회수·알림·커뮤니티·PDF·북마크는 §0 스코프 밖이라 구현하지 않는다.
"""
```

을 다음으로 교체:

```python
"""Step 5. 조립 — 브리핑 마크다운 문서 및 대시보드 HTML 생성.

HTML/CSS 디자인은 대시보드_디자인_개편_명세_v2_SAVE스타일.md(§3 토큰, §9 CSS)를 따른다.
디자인은 네 곳에서만 산다: build_dashboard_html(), build_index_html(), build_archive_html(),
_DASHBOARD_CSS.
조회수·알림·커뮤니티·PDF·북마크는 §0 스코프 밖이라 구현하지 않는다.
"""
```

- [ ] **Step 16: 전체 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step5_assemble.py -v`
Expected: 전부 PASS

Run: `python -m pytest tests/ -v`
Expected: 전체 스위트 PASS

- [ ] **Step 17: 커밋**

```bash
git add src/step5_assemble.py tests/test_step5_assemble.py
git commit -m "feat: generate archive.html from run() alongside dashboard and index"
```
