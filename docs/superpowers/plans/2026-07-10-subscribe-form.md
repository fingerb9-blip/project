# 자동 구독 폼 (구글 폼·CSV 병합) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 방문자가 대시보드의 구글 폼에 이메일을 제출하면 자동으로 구독 명단에 등록되고, 다음 뉴스레터 발송(Step 7)에 자동 반영된다.

**Architecture:** 서버리스. 구글 폼이 응답을 구글 시트에 저장하고, 시트를 "웹에 CSV로 게시"한다. 파이프라인(GitHub Actions)이 그 CSV를 HTTP로 읽어 이메일을 추출하고, 기존 `SUBSCRIBERS`(env, 수동) 명단과 합쳐(∪) 중복 제거 후 발송한다. 대시보드는 구글 폼을 iframe으로 임베드한다.

**Tech Stack:** Python 3.12 표준 라이브러리(`urllib.request`, `csv`, `io`), pytest, 기존 `src/step7_subscriber_email.py`·`src/step5_assemble.py` 확장.

## Global Constraints

- Python 3.12, 표준 라이브러리만 (새 런타임 의존성 금지).
- 구독자 이메일(PII)은 공개 repo에 커밋 금지 — 구글 시트에만 존재. URL 2종은 GitHub Actions Secret으로만 주입.
- 새 코드는 예외를 밖으로 던지지 않는다: CSV 읽기 실패는 `[]` 반환 + 로그(폴백). 발송·파이프라인을 절대 막지 않음.
- 이메일 판정: 셀 값에 `@`가 있고 `@` 뒤 도메인에 `.`이 있으면 이메일로 간주(열 위치 비의존).
- 병합 시 중복 제거하되 입력 순서 유지(env 먼저, 그 다음 CSV).
- 테스트에서 네트워크는 반드시 mock (실제 HTTP 금지). 기존 스타일(한국어 docstring, `from src import ...`).

---

## File Structure

- Modify: `src/step7_subscriber_email.py` — `fetch_csv_subscribers`, `gather_subscribers` 추가, `run()`이 `gather_subscribers` 사용
- Modify: `src/step5_assemble.py` — `build_index_html`에 `subscribe_form_url` 파라미터 + 구독 섹션 렌더
- Modify: `main.py` — `build_index_html` 호출 2곳에 `subscribe_form_url` 전달
- Modify: `.github/workflows/daily_briefing.yml` — `SUBSCRIBE_FORM_URL`, `SUBSCRIBERS_CSV_URL` env 추가
- Test: `tests/test_step7_subscriber_email.py`, `tests/test_step5_assemble.py`

---

## Task 1: 게시 CSV에서 구독자 읽기 `fetch_csv_subscribers`

**Files:**
- Modify: `src/step7_subscriber_email.py`
- Test: `tests/test_step7_subscriber_email.py`

**Interfaces:**
- Consumes: 환경변수 `SUBSCRIBERS_CSV_URL`
- Produces:
  - `_http_get_text(url: str) -> str` — `urllib.request.urlopen(url, timeout=10)`으로 받아 utf-8 디코드. (테스트는 이 함수를 mock)
  - `fetch_csv_subscribers(csv_url: str | None = None) -> list[str]` — None이면 env에서 URL 읽음; 빈 URL이면 `[]`; CSV의 모든 셀에서 이메일처럼 보이는 값만 수집·중복 제거; 어떤 예외도 잡아 `[]` 반환.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_step7_subscriber_email.py 에 추가 (파일 상단에 이미 `from src import step7_subscriber_email as news` 있음)
from unittest.mock import patch

_CSV = (
    "타임스탬프,이메일 주소,수신 동의\n"
    "2026-07-10 09:00:00,alice@x.com,예\n"
    "2026-07-10 09:01:00,bob@y.com,예\n"
    "2026-07-10 09:02:00,alice@x.com,예\n"      # 중복
    "2026-07-10 09:03:00,notanemail,예\n"        # @ 없음
)


def test_fetch_csv_subscribers_extracts_emails_only(monkeypatch):
    monkeypatch.setattr(news, "_http_get_text", lambda url: _CSV)
    assert news.fetch_csv_subscribers("https://sheet/pub.csv") == ["alice@x.com", "bob@y.com"]


def test_fetch_csv_subscribers_empty_url_returns_empty(monkeypatch):
    called = []
    monkeypatch.setattr(news, "_http_get_text", lambda url: called.append(url) or "")
    assert news.fetch_csv_subscribers("") == []
    assert news.fetch_csv_subscribers("   ") == []
    assert called == []  # 빈 URL이면 HTTP 호출조차 안 함


def test_fetch_csv_subscribers_reads_env_when_no_arg(monkeypatch):
    monkeypatch.setenv("SUBSCRIBERS_CSV_URL", "https://sheet/pub.csv")
    monkeypatch.setattr(news, "_http_get_text", lambda url: "이메일\nc@z.com\n")
    assert news.fetch_csv_subscribers() == ["c@z.com"]


def test_fetch_csv_subscribers_returns_empty_on_fetch_error(monkeypatch):
    def boom(url):
        raise OSError("network down")
    monkeypatch.setattr(news, "_http_get_text", boom)
    assert news.fetch_csv_subscribers("https://sheet/pub.csv") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_step7_subscriber_email.py -k fetch_csv -q`
Expected: FAIL (`AttributeError: fetch_csv_subscribers` / `_http_get_text`)

- [ ] **Step 3: Write minimal implementation**

파일 상단 import에 추가: `import csv`, `import io`, `import urllib.request`.

```python
_HTTP_TIMEOUT = 10


def _http_get_text(url: str) -> str:
    """URL 본문을 utf-8 텍스트로 가져온다 (테스트에서 mock되는 경계)."""
    with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT) as resp:  # noqa: S310 - 신뢰된 시트 URL
        return resp.read().decode("utf-8")


def _looks_like_email(value: str) -> bool:
    """셀 값이 이메일 형태인지 판정한다 (@ 있고 도메인에 . 있음)."""
    v = value.strip()
    local, sep, domain = v.partition("@")
    return bool(sep) and bool(local) and "." in domain


def fetch_csv_subscribers(csv_url: str | None = None) -> list[str]:
    """게시된 구글 시트 CSV에서 구독자 이메일을 읽는다.

    열 위치에 의존하지 않고 모든 셀을 훑어 이메일처럼 보이는 값만 수집한다(타임스탬프·동의
    열 자연 배제). 실패(네트워크·파싱) 시 [] 반환(폴백). 빈 URL이면 [].
    """
    if csv_url is None:
        csv_url = os.environ.get("SUBSCRIBERS_CSV_URL", "")
    if not csv_url.strip():
        return []
    try:
        text = _http_get_text(csv_url)
        seen: dict[str, None] = {}
        for row in csv.reader(io.StringIO(text)):
            for cell in row:
                email = cell.strip()
                if _looks_like_email(email) and email not in seen:
                    seen[email] = None
        return list(seen)
    except Exception as exc:  # noqa: BLE001 - CSV 읽기 실패는 폴백(빈 목록)
        logger.error("구독자 CSV 읽기 실패, 무시하고 계속: %s", exc)
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_step7_subscriber_email.py -k fetch_csv -q`
Expected: PASS (4개)

- [ ] **Step 5: Commit**

```bash
git add src/step7_subscriber_email.py tests/test_step7_subscriber_email.py
git commit -m "feat: 게시 CSV에서 구독자 이메일 읽기 fetch_csv_subscribers"
```

---

## Task 2: env+CSV 병합 `gather_subscribers` + run() 연결

**Files:**
- Modify: `src/step7_subscriber_email.py`
- Test: `tests/test_step7_subscriber_email.py`

**Interfaces:**
- Consumes: `load_subscribers()` (env, 기존), `fetch_csv_subscribers()` (Task 1)
- Produces: `gather_subscribers() -> list[str]` — `load_subscribers()`와 `fetch_csv_subscribers()` 결과를 합쳐 중복 제거(env 먼저). `run(...)`의 `subscribers is None` 분기가 이 함수를 사용.

- [ ] **Step 1: Write the failing test**

```python
def test_gather_subscribers_merges_env_and_csv(monkeypatch):
    monkeypatch.setattr(news, "load_subscribers", lambda: ["a@x.com", "b@y.com"])
    monkeypatch.setattr(news, "fetch_csv_subscribers", lambda: ["b@y.com", "c@z.com"])
    # env 먼저, CSV의 중복(b@y.com) 제거, 순서 유지
    assert news.gather_subscribers() == ["a@x.com", "b@y.com", "c@z.com"]


def test_run_uses_gather_subscribers_when_no_list(tmp_path, monkeypatch):
    # subscribers=None이면 gather_subscribers 경로를 탄다.
    dash = tmp_path / "dashboard"; dash.mkdir()
    (dash / "2026-07-11.html").write_text(
        '<html><head><link rel="stylesheet" href="style.css"></head><body>x</body></html>',
        encoding="utf-8")
    summ = tmp_path / "summarized" / "2026-07-11.json"
    summ.parent.mkdir(parents=True, exist_ok=True)
    summ.write_text("[]", encoding="utf-8")
    state = tmp_path / "state" / "newsletter_state.json"
    monkeypatch.setattr(news, "gather_subscribers", lambda: ["z@z.com"])
    with patch("src.step7_subscriber_email._send_html_email") as send:
        result = news.run(dash, summ, state, "2026-07-11", "https://site/")
    send.assert_called_once()
    assert send.call_args.args[0] == "z@z.com"
    assert result["sent"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_step7_subscriber_email.py -k "gather or uses_gather" -q`
Expected: FAIL (`AttributeError: gather_subscribers`, 그리고 run이 아직 load_subscribers를 씀)

- [ ] **Step 3: Write minimal implementation**

`fetch_csv_subscribers` 아래에 추가:

```python
def gather_subscribers() -> list[str]:
    """수동 명단(env)과 게시 CSV 명단을 합쳐 중복 제거한다(env 먼저, 순서 유지)."""
    seen: dict[str, None] = {}
    for email in [*load_subscribers(), *fetch_csv_subscribers()]:
        if email not in seen:
            seen[email] = None
    return list(seen)
```

그리고 `run(...)` 안의 다음 두 줄:

```python
        if subscribers is None:
            subscribers = load_subscribers()
```

을 이렇게 바꾼다:

```python
        if subscribers is None:
            subscribers = gather_subscribers()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_step7_subscriber_email.py -q`
Expected: PASS (기존 + 신규 전체)

- [ ] **Step 5: Commit**

```bash
git add src/step7_subscriber_email.py tests/test_step7_subscriber_email.py
git commit -m "feat: env+CSV 구독자 병합 gather_subscribers + run 연결"
```

---

## Task 3: 대시보드에 구글 폼 임베드

**Files:**
- Modify: `src/step5_assemble.py` (`build_index_html` 및 신규 `_build_subscribe_section`)
- Modify: `main.py` (`build_index_html` 호출 2곳)
- Test: `tests/test_step5_assemble.py`

**Interfaces:**
- Consumes: 환경변수 `SUBSCRIBE_FORM_URL` (main.py가 읽어 전달)
- Produces: `build_index_html(..., subscribe_form_url: str | None = None)` — URL이 있으면 구독 폼 iframe 섹션을 포함, 없으면 생략.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_step5_assemble.py 에 추가 (파일 상단에 import json, from src import step5_assemble 있음)
def _index_state(tmp_path):
    state = tmp_path / "run_status.json"
    state.write_text(json.dumps({"last_run_date": "2026-07-10", "last_run_status": "success"}),
                     encoding="utf-8")
    return state


def test_build_index_shows_subscribe_iframe_when_url_set(tmp_path):
    dashboard_dir = tmp_path / "dashboard"; dashboard_dir.mkdir()
    out = step5_assemble.build_index_html(
        dashboard_dir, _index_state(tmp_path),
        subscribe_form_url="https://forms.example/x",
    )
    assert "뉴스레터 구독" in out
    assert 'src="https://forms.example/x"' in out


def test_build_index_omits_subscribe_when_no_url(tmp_path):
    dashboard_dir = tmp_path / "dashboard"; dashboard_dir.mkdir()
    out = step5_assemble.build_index_html(dashboard_dir, _index_state(tmp_path))
    assert "뉴스레터 구독" not in out


def test_build_index_escapes_subscribe_url(tmp_path):
    dashboard_dir = tmp_path / "dashboard"; dashboard_dir.mkdir()
    out = step5_assemble.build_index_html(
        dashboard_dir, _index_state(tmp_path),
        subscribe_form_url='https://f/x"><script>alert(1)</script>',
    )
    assert "<script>alert(1)</script>" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_step5_assemble.py -k subscribe -q`
Expected: FAIL (`build_index_html() got an unexpected keyword argument 'subscribe_form_url'`)

- [ ] **Step 3: Write minimal implementation**

(a) `_build_date_select` 근처(모듈 상단 헬퍼들 사이)에 헬퍼 추가:

```python
def _build_subscribe_section(subscribe_form_url: str | None) -> str:
    """구글 폼을 임베드한 '뉴스레터 구독' 섹션. URL이 없으면 빈 문자열."""
    if not subscribe_form_url:
        return ""
    url = _esc(subscribe_form_url)
    return (
        '<section class="subscribe"><h2 class="sec">뉴스레터 구독</h2>'
        "<p>매일 아침 브리핑을 이메일로 받아보세요.</p>"
        f'<iframe src="{url}" title="뉴스레터 구독 폼" loading="lazy" '
        'style="width:100%;max-width:640px;height:520px;border:0"></iframe>'
        "</section>"
    )
```

(b) `build_index_html` 시그니처에 파라미터 추가 (기존 시그니처 끝에):

```python
    cold_start_stage: str = "active",
    subscribe_form_url: str | None = None,
) -> str:
```

(c) `build_index_html` 본문에서 `<p class="site-footer">`를 append하기 직전에 구독 섹션을 삽입한다. 즉 site-footer append 라인 바로 위에:

```python
    parts.append(_build_subscribe_section(subscribe_form_url))
```

(만약 `build_index_html`에 site-footer append가 없으면, `</body>`를 붙이는 마지막 append 직전에 넣는다.)

(d) `main.py`의 `build_index_html` 호출 2곳(성공 경로 ~224행, 실패 경로 ~196행) 모두에 인자를 추가한다:

```python
            subscribe_form_url=os.environ.get("SUBSCRIBE_FORM_URL"),
```

(`main.py`에 `import os`가 이미 있다 — Step 7 뉴스레터 작업에서 추가됨.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_step5_assemble.py -k subscribe -q`
Expected: PASS (3개)

- [ ] **Step 5: Run full suite (회귀 확인)**

Run: `python -m pytest -q`
Expected: PASS (전체). `scripts/rebuild_dashboard.py`는 `build_index_html`을 새 인자 없이 호출하므로 기본값 None으로 안전하다.

- [ ] **Step 6: Commit**

```bash
git add src/step5_assemble.py main.py tests/test_step5_assemble.py
git commit -m "feat: 대시보드에 구글 폼 구독 섹션 임베드(SUBSCRIBE_FORM_URL)"
```

---

## Task 4: GitHub Actions 워크플로 env + 셋업 안내

**Files:**
- Modify: `.github/workflows/daily_briefing.yml`

**Interfaces:**
- Consumes: GitHub Actions Secret `SUBSCRIBE_FORM_URL`, `SUBSCRIBERS_CSV_URL`

- [ ] **Step 1: 워크플로 env 추가**

`.github/workflows/daily_briefing.yml`의 `Run pipeline` 스텝 `env:` 블록(이미 `SUBSCRIBERS`, `DASHBOARD_URL` 등이 있음)에 같은 들여쓰기로 두 줄 추가:

```yaml
          SUBSCRIBE_FORM_URL: ${{ secrets.SUBSCRIBE_FORM_URL }}
          SUBSCRIBERS_CSV_URL: ${{ secrets.SUBSCRIBERS_CSV_URL }}
```

- [ ] **Step 2: YAML 유효성 확인**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily_briefing.yml', encoding='utf-8')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: 셋업 안내 (수동, 사용자 작업 — 보고서에 기록)**

- 구글 폼 생성: 질문 = 이메일(단답형), "뉴스레터 수신에 동의합니다"(체크박스). 응답 → 시트 자동 연결.
- 응답 시트 → 파일 → 공유 → **웹에 게시 → 쉼표로 구분된 값(.csv)** → URL 복사 → Secret `SUBSCRIBERS_CSV_URL`.
- 폼 → 보내기 → `< >`(임베드 HTML)의 `src` URL 복사 → Secret `SUBSCRIBE_FORM_URL`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/daily_briefing.yml
git commit -m "ci: daily-briefing에 SUBSCRIBE_FORM_URL/SUBSCRIBERS_CSV_URL env 전달"
```

---

## Self-Review (작성자 확인 완료)

- **스펙 커버리지:** CSV 읽기(T1)·env+CSV 병합/run 연결(T2)·대시보드 폼 임베드(T3)·워크플로 env+셋업(T4) — 스펙 2~5·7장 매핑됨.
- **플레이스홀더:** 없음. 모든 코드/명령/기대값 실체 포함.
- **타입 일관성:** `fetch_csv_subscribers(csv_url=None)->list[str]`, `gather_subscribers()->list[str]`가 T1·T2에서 일치. `run()`은 `gather_subscribers`로 교체(기존 반환 `{"sent","failed","skipped"}` 유지). `build_index_html`의 신규 `subscribe_form_url` 파라미터가 T3 테스트·main 호출부와 일치. `_http_get_text`가 T1 구현과 테스트 mock 대상으로 일치.
- **범위:** 단일 구현 계획으로 적정.
