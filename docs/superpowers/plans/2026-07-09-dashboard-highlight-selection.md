# 대시보드 "오늘의 핵심" 하이라이트 선정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `build_dashboard_html()`의 "오늘의 핵심" 섹션이 현재는 전체 요약 기사를 그냥 나열만 하고 있어("헤딩만 있고 실제 하이라이트가 없음") — 신규 `select_highlights()`로 확정 우선·카테고리 다양성·최신순 기준 3~5개를 선정해 상단에 눈에 띄는 카드로 렌더링한다.

**Architecture:** 기존 전체 피드(`#feed`, `_build_article_card`)는 그대로 두고, 그 위에 별도의 가로 스크롤 "하이라이트 스트립"을 추가한다. 선정 로직(`select_highlights`)과 렌더링(`_build_highlight_card`/`_build_highlight_strip`)을 분리해, 선정 기준이 바뀌어도 렌더링에 영향이 없게 한다.

**Tech Stack:** Python 3.10+, pytest (기존 `tests/test_step5_assemble.py` 패턴과 동일)

## Global Constraints

- `build_dashboard_html()`의 기존 파라미터 시그니처는 바꾸지 않는다 (`run()`에서의 호출 방식 호환 유지).
- 디자인은 `src/step5_assemble.py`의 `build_dashboard_html()`, `build_index_html()`, `_DASHBOARD_CSS` 세 곳에서만 산다(파일 상단 docstring, L4) — CSS는 `_DASHBOARD_CSS` 상수에만 추가한다.
- 외부 소스 텍스트(제목·요약)는 반드시 `_esc()`로 이스케이프하고, URL은 `_safe_url()`을 통과시킨다 (XSS 방지 원칙, `docs/phase1_ipo.md` Step 5).
- 요약이 없는 기사(`summary_fallback` truthy 또는 `summary` 없음/빈 값)는 하이라이트 후보에서 제외한다.
- 카테고리 다양성은 기사에 이미 부여된 `article["category"]`(Step 3가 `config/categories.yaml` 기준으로 분류한 결과)를 그대로 사용한다 — `select_highlights()`가 `config/categories.yaml`을 별도로 다시 로드하지 않는다 (이미 분류된 카테고리 태그를 신뢰).
- 테스트는 `python -m pytest tests/test_step5_assemble.py -v` 로 실행한다 (프로젝트 루트에서).

---

## Task 1: `select_highlights()` 선정 로직 + 하이라이트 카드 렌더링 + CSS

**배경 (현재 로직):**
- `build_dashboard_html()`(`src/step5_assemble.py:361-468`)의 "오늘의 핵심" 섹션(L411-421)은 `summarized_articles`(이미 "핵심" tier로 필터링된 기사 전체)를 필터 토글 아래 `#feed` div에 `_build_article_card()`로 전부 나열한다. 몇 개가 오든 선별 없이 다 보여주는 피드일 뿐, "핵심 중에서도 더 핵심"을 짚어주는 하이라이트 UI가 없다.
- `src/step4_summarize.py:65`의 `tag_confirmation_level()`은 문자열 `"[확정]"` 또는 `"[관측]"`을 반환해 `article["confirmation_tag"]`에 저장한다(별도의 `confirmation_level` 필드는 없음). 기존 코드(`_build_article_card`, L312-318)도 `"확정" in tag`/`"관측" in tag` 부분 문자열 매칭으로 판정하는 패턴을 쓰고 있으므로, 신규 로직도 동일하게 `"확정" in (article.get("confirmation_tag") or "")`로 판정한다.
- `_CATEGORY_ORDER = ["메모리", "파운드리", "장비·소재", "팹리스·설계", "규제·정책"]`(L22)는 pill 필터 정렬용으로만 쓰인다. 하이라이트의 "카테고리 다양성"은 이 순서를 강제하는 게 아니라 "이미 선택된 카테고리와 겹치지 않는 기사를 우선"하는 방식으로 구현한다(아래 알고리즘 참고).

**선정 알고리즘 (`select_highlights`):**
1. 후보 필터링: `summary_fallback`이 참이거나 `summary`가 없는/빈 기사는 제외.
2. 정렬: `(확정 여부 아님, -최신순 타임스탬프)` 튜플로 정렬 — 확정 기사가 앞으로, 동일 확정 여부 내에서는 최신 기사가 앞으로.
3. 그리디 선택: 정렬된 순서대로 순회하며, 해당 기사의 카테고리 집합이 이미 선택된 기사들의 카테고리 집합과 겹치지 않으면 선택(1라운드). `max_count`(기본 5)에 도달하면 종료.
4. 1라운드로 `max_count`를 못 채웠으면, 카테고리 중복을 허용하고 정렬 순서대로 나머지를 채운다(2라운드).
5. 후보가 `max_count`보다 적으면 있는 만큼만 반환한다(3개 미만이어도 에러 없음).

**Files:**
- Modify: `src/step5_assemble.py`
- Test: `tests/test_step5_assemble.py`

**Interfaces:**
- Produces: `step5_assemble.select_highlights(articles: list[dict], max_count: int = 5) -> list[dict]`, `step5_assemble._highlight_sort_timestamp(article: dict) -> float`, `step5_assemble._build_highlight_card(article: dict) -> str`, `step5_assemble._build_highlight_strip(articles: list[dict]) -> str`
- Consumes (기존): `article["summary"]`, `article["summary_fallback"]`, `article["confirmation_tag"]`, `article["category"]`, `article["published_at"]`, `article["title"]`, `article["url"]` — 전부 Step 4 결과 스키마에 이미 존재하는 필드. `_esc()`, `_safe_url()` 재사용.

- [ ] **Step 1: `select_highlights()` — 요약 없는 기사 제외 + 확정 우선 — 실패하는 테스트부터**

`tests/test_step5_assemble.py`에 추가 (파일 하단, 기존 테스트들 아래):

```python
def test_select_highlights_excludes_articles_without_summary():
    no_summary = _sample_article(id="a1", summary=None, summary_fallback=True)
    has_summary = _sample_article(id="a2", summary="요약 있음", summary_fallback=False)

    result = step5_assemble.select_highlights([no_summary, has_summary])

    assert [a["id"] for a in result] == ["a2"]


def test_select_highlights_excludes_articles_with_empty_summary_string():
    empty_summary = _sample_article(id="a1", summary="", summary_fallback=False)
    result = step5_assemble.select_highlights([empty_summary])
    assert result == []


def test_select_highlights_prefers_confirmed_over_observed():
    observed = _sample_article(
        id="a1", confirmation_tag="[관측]", category=["메모리"],
        published_at="2026-07-09T09:00:00+09:00",
    )
    confirmed = _sample_article(
        id="a2", confirmation_tag="[확정]", category=["파운드리"],
        published_at="2026-07-09T08:00:00+09:00",  # 더 오래됐지만 확정이라 우선
    )

    result = step5_assemble.select_highlights([observed, confirmed], max_count=1)

    assert [a["id"] for a in result] == ["a2"]
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k select_highlights -v`
Expected: 3개 모두 `AttributeError: module 'src.step5_assemble' has no attribute 'select_highlights'`로 FAIL

- [ ] **Step 3: `select_highlights()`, `_highlight_sort_timestamp()` 구현**

`src/step5_assemble.py`의 상단 상수 블록(L22-26 부근, `_CATEGORY_ORDER` 다음 줄)에 추가:

```python
_HIGHLIGHT_MAX_COUNT = 5
```

`_build_article_card()` 함수(L291-358) 바로 뒤에 추가:

```python
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
    (summary_fallback 또는 summary 미기재)는 후보에서 제외한다.

    Args:
        articles: Step 4 결과 기사 리스트 ("핵심" tier, 요약 포함)
        max_count: 최대 선정 개수 (기본 5)

    Returns:
        하이라이트로 선정된 기사 리스트. 후보가 부족하면 max_count보다 적게 반환한다.
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
            break
        selected.append(article)

    return selected
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k select_highlights -v`
Expected: 3개 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/step5_assemble.py tests/test_step5_assemble.py
git commit -m "feat: add select_highlights() for dashboard today's-picks selection"
```

---

- [ ] **Step 6: 카테고리 다양성 + 최신순 + max_count — 실패하는 테스트부터**

`tests/test_step5_assemble.py`에 추가:

```python
def test_select_highlights_maximizes_category_diversity():
    memory1 = _sample_article(
        id="a1", category=["메모리"], published_at="2026-07-09T10:00:00+09:00",
    )
    memory2 = _sample_article(
        id="a2", category=["메모리"], published_at="2026-07-09T09:00:00+09:00",
    )
    foundry = _sample_article(
        id="a3", category=["파운드리"], published_at="2026-07-09T08:00:00+09:00",
    )

    result = step5_assemble.select_highlights([memory1, memory2, foundry], max_count=2)

    assert [a["id"] for a in result] == ["a1", "a3"]  # 메모리 중복(a2)보다 다른 카테고리(a3) 우선


def test_select_highlights_backfills_with_duplicate_category_when_not_enough_diversity():
    memory1 = _sample_article(
        id="a1", category=["메모리"], published_at="2026-07-09T10:00:00+09:00",
    )
    memory2 = _sample_article(
        id="a2", category=["메모리"], published_at="2026-07-09T09:00:00+09:00",
    )

    result = step5_assemble.select_highlights([memory1, memory2], max_count=2)

    assert [a["id"] for a in result] == ["a1", "a2"]  # 카테고리가 겹쳐도 max_count까지 채움


def test_select_highlights_sorts_by_recency_within_same_confirmation_level():
    older = _sample_article(
        id="a1", category=["메모리"], published_at="2026-07-08T09:00:00+09:00",
    )
    newer = _sample_article(
        id="a2", category=["파운드리"], published_at="2026-07-09T09:00:00+09:00",
    )

    result = step5_assemble.select_highlights([older, newer])

    assert [a["id"] for a in result] == ["a2", "a1"]


def test_select_highlights_returns_fewer_than_max_count_when_not_enough_candidates():
    only_one = _sample_article(id="a1")
    result = step5_assemble.select_highlights([only_one], max_count=5)
    assert len(result) == 1


def test_select_highlights_respects_max_count_cap():
    articles = [
        _sample_article(id=f"a{i}", category=[f"cat{i}"], published_at="2026-07-09T09:00:00+09:00")
        for i in range(8)
    ]
    result = step5_assemble.select_highlights(articles, max_count=5)
    assert len(result) == 5
```

- [ ] **Step 7: 테스트 실행 → 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k select_highlights -v`
Expected: 이미 Step 3 구현이 이 요구사항까지 함께 충족하므로 전부 PASS (별도 구현 변경 불필요). PASS하지 않으면 Step 3 구현을 다시 점검한다.

- [ ] **Step 8: 커밋 (테스트 추가분)**

```bash
git add tests/test_step5_assemble.py
git commit -m "test: cover category diversity, recency, and max_count for select_highlights"
```

---

- [ ] **Step 9: 하이라이트 카드 렌더링 — 실패하는 테스트부터**

`tests/test_step5_assemble.py`에 추가:

```python
def test_build_dashboard_html_renders_highlight_strip():
    article = _sample_article(title="하이라이트 대상 기사")
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'class="highlight-strip"' in html_out
    assert 'class="highlight-card"' in html_out
    assert "하이라이트 대상 기사" in html_out


def test_build_dashboard_html_highlight_card_escapes_title():
    malicious = _sample_article(title="<script>alert(1)</script>")
    html_out = step5_assemble.build_dashboard_html([malicious], [], {}, "2026-07-08")
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out


def test_build_dashboard_html_highlight_card_shows_category_chip():
    article = _sample_article(category=["메모리"])
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    assert 'class="highlight-strip"' in html_out
    assert "메모리" in html_out


def test_build_dashboard_html_omits_highlight_strip_when_no_eligible_articles():
    no_summary = _sample_article(summary=None, summary_fallback=True)
    html_out = step5_assemble.build_dashboard_html([no_summary], [], {}, "2026-07-08")
    assert 'class="highlight-strip"' not in html_out


def test_build_dashboard_html_highlight_strip_appears_before_full_feed():
    article = _sample_article()
    html_out = step5_assemble.build_dashboard_html([article], [], {}, "2026-07-08")
    highlight_pos = html_out.index('class="highlight-strip"')
    feed_pos = html_out.index('id="feed"')
    assert highlight_pos < feed_pos
```

- [ ] **Step 10: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k highlight -v`
Expected: 5개 모두 FAIL (`class="highlight-strip"`가 출력에 없음)

- [ ] **Step 11: `_build_highlight_card()`, `_build_highlight_strip()` 구현 + `build_dashboard_html()` 연결**

`_build_article_card()` 다음, `select_highlights()`/`_highlight_sort_timestamp()` 다음에 추가:

```python
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
        tag_class = "ok"
    elif "관측" in tag:
        tag_class = "obs"
    else:
        tag_class = "mut"

    parts = ['<article class="highlight-card">']
    parts.append('<div class="row">')
    if tag:
        parts.append(f'<span class="tag {tag_class}">{_esc(tag)}</span>')
    for category in article.get("category") or []:
        parts.append(f'<span class="chip">{_esc(category)}</span>')
    parts.append("</div>")
    parts.append(f'<p class="title">{link_open}{title}{link_close}</p>')
    parts.append(f'<p class="summary">{_esc(article["summary"])}</p>')
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
```

`build_dashboard_html()`(L361-468) 안의 아래 부분:

```python
    parts.append('<h2 class="sec">오늘의 핵심</h2>')
    parts.append(
        '<label class="filter-toggle"><input type="checkbox" id="deep-tech-filter"> '
        "학회·특허만 보기</label>"
    )
```

을 다음으로 교체 (하이라이트 스트립을 헤딩 바로 다음, 토글 위에 삽입):

```python
    parts.append('<h2 class="sec">오늘의 핵심</h2>')
    parts.append(_build_highlight_strip(select_highlights(summarized_articles)))
    parts.append(
        '<label class="filter-toggle"><input type="checkbox" id="deep-tech-filter"> '
        "학회·특허만 보기</label>"
    )
```

- [ ] **Step 12: 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k highlight -v`
Expected: 5개 모두 PASS

- [ ] **Step 13: CSS 추가**

`_DASHBOARD_CSS`(L944 부근) 안의 "카드 공통" 블록 —

```css
.cardfoot{display:flex;align-items:center;justify-content:space-between;margin-top:.5rem}
.cardfoot a{font-size:.85rem}
```

바로 다음 줄에 추가 (배지·칩 블록 앞):

```css

/* 오늘의 핵심 하이라이트 */
.highlight-strip{display:flex;gap:10px;overflow-x:auto;padding-bottom:6px;margin:0 0 14px;scroll-snap-type:x proximity}
.highlight-card{flex:0 0 220px;scroll-snap-align:start;background:var(--surface);
  border:1px solid var(--line);border-left:3px solid var(--brand);border-radius:14px;padding:13px 14px}
.highlight-card .title{font-size:.92rem;margin:.5rem 0;-webkit-line-clamp:2}
.highlight-card .summary{font-size:.82rem;margin:.3rem 0;
  display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}
```

(기존 `.title`/`.summary`는 이미 `-webkit-line-clamp` 등 공통 속성을 갖고 있으므로, 위 규칙은 `.highlight-card` 안에서만 폰트 크기·줄 수를 덮어쓴다 — CSS 상속 순서상 `.highlight-card .title`이 `.title`보다 더 구체적이라 정상 적용된다.)

- [ ] **Step 14: 전체 테스트 실행 → 통과 확인**

Run: `python -m pytest tests/test_step5_assemble.py -v`
Expected: 전부 PASS

Run: `python -m pytest tests/ -v`
Expected: 전체 스위트 PASS (다른 Step 테스트에 영향 없어야 함)

- [ ] **Step 15: 커밋**

```bash
git add src/step5_assemble.py
git commit -m "feat: render highlight strip in dashboard today's-picks section"
```
