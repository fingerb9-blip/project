# 이메일 뉴스레터 발송 (Step 7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매일 파이프라인이 브리핑을 발행한 뒤, 명단의 구독자에게 그날 브리핑을 이메일(오늘의 핵심 3개 본문 + 자립형 HTML 첨부)로 발송한다.

**Architecture:** 기존 Step 0~6은 그대로 두고, Step 6 성공 직후 실행되는 신규 모듈 `src/step7_subscriber_email.py`를 추가한다. 결제·회원가입·DB 없음. 구독자 명단은 환경변수(GitHub Actions Secret), 발송은 기존 Gmail SMTP를 재사용한다. Step 7의 어떤 실패도 파이프라인 종료 코드에 영향을 주지 않는다.

**Tech Stack:** Python 3.12, 표준 라이브러리 `smtplib`/`email`(MIME), pytest, 기존 `src/step5_assemble` 재사용.

## Global Constraints

- Python 3.12, 외부 유료 서비스/새 런타임 의존성 추가 금지 (표준 라이브러리만 사용).
- 구독자 이메일(PII)은 **공개 저장소에 절대 커밋 금지** — `SUBSCRIBERS` 환경변수(GitHub Actions Secret)로만 주입, 로컬은 `.env`.
- SMTP 자격은 기존 환경변수 재사용: `SMTP_HOST`, `SMTP_PORT`(기본 587), `SMTP_USER`, `SMTP_PASSWORD`.
- Step 7은 예외를 밖으로 던지지 않는다(내부에서 모두 흡수·로그). 파이프라인·대시보드는 이미 발행된 상태이므로 발송 실패가 실행을 실패로 만들면 안 된다.
- 하루 1회만 발송(중복 방지). `FORCE_RESEND=true`일 때만 재발송.
- 테스트에서 SMTP는 반드시 mock (실제 메일 발송 금지).
- 기존 코드 스타일(한국어 docstring, `from src import ...`) 준수.

---

## File Structure

- Create: `src/step7_subscriber_email.py` — 명단 로드 · 자립형 HTML · 본문 · 발송 · 상태·오케스트레이션
- Create: `tests/test_step7_subscriber_email.py` — 위 모듈의 단위 테스트
- Modify: `main.py` — Step 6 성공 후 `_maybe_send_newsletter(...)` 호출 (예외 흡수 래퍼)
- Modify: `tests/test_main.py` (없으면 Create) — `_maybe_send_newsletter` 래퍼 테스트
- Modify: `.github/workflows/daily_briefing.yml` — `Run pipeline` 스텝 env에 `SUBSCRIBERS`, `DASHBOARD_URL` 추가
- Modify: `docs/phase*_ipo.md` 아님 — 대신 `README`/설정 안내는 스펙 문서로 갈음 (신규 문서 불필요)

상태 파일: `data/state/newsletter_state.json` (`{"last_sent_date": "YYYY-MM-DD", "sent_count": N}`) — 코드가 자동 생성.

---

## Task 1: 구독자 명단 로더 `load_subscribers`

**Files:**
- Create: `src/step7_subscriber_email.py`
- Test: `tests/test_step7_subscriber_email.py`

**Interfaces:**
- Consumes: 환경변수 `SUBSCRIBERS` (콤마 구분 이메일 문자열)
- Produces: `load_subscribers(raw: str | None = None) -> list[str]` — `raw`가 None이면 `os.environ["SUBSCRIBERS"]`(없으면 빈 문자열)에서 읽는다. 콤마 분리·공백 제거·`@` 포함 항목만·중복 제거(입력 순서 유지). 유효 항목이 없으면 `[]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_step7_subscriber_email.py
from src import step7_subscriber_email as news


def test_load_subscribers_parses_and_cleans():
    raw = "a@x.com, b@y.com ,a@x.com,  , notanemail , c@z.com"
    assert news.load_subscribers(raw) == ["a@x.com", "b@y.com", "c@z.com"]


def test_load_subscribers_empty_returns_empty_list():
    assert news.load_subscribers("") == []
    assert news.load_subscribers("   ,  ") == []


def test_load_subscribers_reads_env_when_no_arg(monkeypatch):
    monkeypatch.setenv("SUBSCRIBERS", "only@x.com")
    assert news.load_subscribers() == ["only@x.com"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_step7_subscriber_email.py -q`
Expected: FAIL (`ModuleNotFoundError: src.step7_subscriber_email` 또는 `AttributeError`)

- [ ] **Step 3: Write minimal implementation**

```python
# src/step7_subscriber_email.py
"""Step 7. 이메일 뉴스레터 — 명단 구독자에게 그날 브리핑을 발송한다 (무료, 지인 대상)."""

import logging
import os

logger = logging.getLogger(__name__)


def load_subscribers(raw: str | None = None) -> list[str]:
    """구독자 명단을 로드한다.

    Args:
        raw: 콤마 구분 이메일 문자열. None이면 환경변수 SUBSCRIBERS에서 읽는다.

    Returns:
        정제된 이메일 리스트 (공백 제거·'@' 포함·중복 제거, 입력 순서 유지). 없으면 [].
    """
    if raw is None:
        raw = os.environ.get("SUBSCRIBERS", "")
    seen: dict[str, None] = {}
    for part in raw.split(","):
        email = part.strip()
        if "@" in email and email not in seen:
            seen[email] = None
    return list(seen)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_step7_subscriber_email.py -q`
Expected: PASS (3개)

- [ ] **Step 5: Commit**

```bash
git add src/step7_subscriber_email.py tests/test_step7_subscriber_email.py
git commit -m "feat: Step 7 구독자 명단 로더 load_subscribers"
```

---

## Task 2: 자립형 HTML 생성 `build_standalone_html`

**Files:**
- Modify: `src/step7_subscriber_email.py`
- Test: `tests/test_step7_subscriber_email.py`

**Interfaces:**
- Consumes: `data/dashboard/{today}.html`, `src.step5_assemble._DASHBOARD_CSS`
- Produces: `build_standalone_html(dashboard_dir: Path, today: str) -> str` — `{today}.html`을 읽어 `<link rel="stylesheet" href="style.css">`를 `<style>…CSS…</style>`로 치환한 자립형 HTML 문자열을 반환. 파일이 없으면 `FileNotFoundError`.

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from src import step5_assemble


def test_build_standalone_html_inlines_css(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "2026-07-11.html").write_text(
        '<html><head><link rel="stylesheet" href="style.css"></head>'
        "<body>본문</body></html>",
        encoding="utf-8",
    )

    out = news.build_standalone_html(dashboard_dir, "2026-07-11")

    assert '<link rel="stylesheet" href="style.css">' not in out
    assert "<style>" in out
    # 실제 대시보드 CSS의 일부가 인라인됐는지 확인
    assert step5_assemble._DASHBOARD_CSS[:40] in out
    assert "본문" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_step7_subscriber_email.py::test_build_standalone_html_inlines_css -q`
Expected: FAIL (`AttributeError: build_standalone_html`)

- [ ] **Step 3: Write minimal implementation**

먼저 파일 상단 import에 `Path`와 `step5_assemble`를 추가한다:

```python
from pathlib import Path

from src import step5_assemble
```

그리고 함수 추가:

```python
_STYLE_LINK = '<link rel="stylesheet" href="style.css">'


def build_standalone_html(dashboard_dir: Path, today: str) -> str:
    """그날 대시보드 HTML의 외부 CSS 링크를 인라인 <style>로 치환한 자립형 HTML을 만든다.

    이메일 첨부는 style.css를 함께 못 보내므로, 브라우저에서 단독으로 열어도 스타일이
    유지되도록 CSS를 문서 안에 넣는다.
    """
    html_text = (Path(dashboard_dir) / f"{today}.html").read_text(encoding="utf-8")
    inline_style = f"<style>{step5_assemble._DASHBOARD_CSS}</style>"
    return html_text.replace(_STYLE_LINK, inline_style)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_step7_subscriber_email.py::test_build_standalone_html_inlines_css -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/step7_subscriber_email.py tests/test_step7_subscriber_email.py
git commit -m "feat: Step 7 자립형 HTML 생성 build_standalone_html"
```

---

## Task 3: 메일 본문 생성 `build_email_body`

**Files:**
- Modify: `src/step7_subscriber_email.py`
- Test: `tests/test_step7_subscriber_email.py`

**Interfaces:**
- Consumes: `data/summarized/{today}.json` (핵심 기사 리스트), `src.step5_assemble.select_highlights`
- Produces: `build_email_body(summarized_path: Path, today: str, dashboard_url: str) -> str` — 요약 데이터에서 상위 3개를 뽑아 `제목 + [확정]/[관측] + 한 줄 요약`으로 렌더한 HTML 본문. 대시보드 링크와 구독취소 안내 포함. 파일이 없거나 핵심이 없으면 "오늘은 핵심 기사가 없습니다" 안내를 포함한 본문을 반환.

- [ ] **Step 1: Write the failing test**

```python
import json


def _write_summarized(path, articles):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(articles, ensure_ascii=False), encoding="utf-8")


def test_build_email_body_includes_top_three_and_footer(tmp_path):
    path = tmp_path / "summarized" / "2026-07-11.json"
    arts = [
        {"id": f"a{i}", "title": f"기사{i}", "url": f"https://ex.com/{i}",
         "source": "디일렉", "summary": f"요약{i}", "confirmation_tag": "[확정]",
         "summary_fallback": False, "category": [f"c{i}"], "tier": "핵심"}
        for i in range(5)
    ]
    _write_summarized(path, arts)

    body = news.build_email_body(path, "2026-07-11", "https://site.example/")

    # 상위 3개만 본문에 (select_highlights 기본 규칙상 최대 3개 요청)
    assert body.count('href="https://ex.com/') == 3
    assert "https://site.example/" in body       # 대시보드 링크
    assert "구독" in body and "회신" in body        # 구독취소 안내
    assert "[확정]" in body


def test_build_email_body_handles_no_core(tmp_path):
    path = tmp_path / "summarized" / "2026-07-11.json"
    _write_summarized(path, [])
    body = news.build_email_body(path, "2026-07-11", "https://site.example/")
    assert "핵심 기사가 없습니다" in body
    assert "https://site.example/" in body


def test_build_email_body_missing_file_is_safe(tmp_path):
    path = tmp_path / "summarized" / "2026-07-11.json"  # 존재하지 않음
    body = news.build_email_body(path, "2026-07-11", "https://site.example/")
    assert "핵심 기사가 없습니다" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_step7_subscriber_email.py -k build_email_body -q`
Expected: FAIL (`AttributeError: build_email_body`)

- [ ] **Step 3: Write minimal implementation**

파일 상단 import에 `json`과 `html`을 추가한다 (`import json`, `import html`).

```python
def _load_core_articles(summarized_path: Path) -> list[dict]:
    path = Path(summarized_path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    articles = data if isinstance(data, list) else data.get("articles", [])
    return [a for a in articles if a.get("tier", "핵심") == "핵심"]


def build_email_body(summarized_path: Path, today: str, dashboard_url: str) -> str:
    """이메일 본문(HTML)을 만든다. 오늘의 핵심 상위 3개 + 대시보드 링크 + 구독취소 안내."""
    core = _load_core_articles(summarized_path)
    highlights = step5_assemble.select_highlights(core, max_count=3) if core else []

    parts = [f"<h2>반도체 브리핑 · {html.escape(today)} 오늘의 핵심</h2>"]
    if not highlights:
        parts.append("<p>오늘은 핵심 기사가 없습니다. 전체 목록은 대시보드에서 확인해 주세요.</p>")
    else:
        parts.append("<ul>")
        for a in highlights:
            tag = html.escape(a.get("confirmation_tag") or "")
            title = html.escape(a.get("title", ""))
            url = html.escape(a.get("url", ""))
            summary = html.escape((a.get("summary") or "")[:200])
            parts.append(
                f'<li><a href="{url}">{tag} {title}</a><br>{summary}</li>'
            )
        parts.append("</ul>")

    parts.append(
        f'<p>전체 브리핑은 첨부 파일 또는 '
        f'<a href="{html.escape(dashboard_url)}">대시보드</a>에서 보실 수 있습니다.</p>'
    )
    parts.append(
        '<hr><p style="color:#888;font-size:12px">'
        "이 메일은 수신에 동의하신 분께만 발송됩니다. "
        "구독을 원치 않으시면 이 메일에 회신해 주세요.</p>"
    )
    return "".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_step7_subscriber_email.py -k build_email_body -q`
Expected: PASS (3개)

- [ ] **Step 5: Commit**

```bash
git add src/step7_subscriber_email.py tests/test_step7_subscriber_email.py
git commit -m "feat: Step 7 메일 본문 생성 build_email_body (상위 3개 + 링크 + 구독취소)"
```

---

## Task 4: 발송·상태·오케스트레이션 `run`

**Files:**
- Modify: `src/step7_subscriber_email.py`
- Test: `tests/test_step7_subscriber_email.py`

**Interfaces:**
- Consumes: Task 1~3 함수, 환경변수 `SMTP_*`/`DASHBOARD_URL`/`FORCE_RESEND`
- Produces:
  - `_send_html_email(to_addr: str, subject: str, html_body: str, attachment_name: str, attachment_html: str) -> None` — SMTP로 HTML 본문 + HTML 첨부 1개를 발송. 실패 시 예외를 던진다(호출부가 건별 처리).
  - `load_send_state(state_path: Path) -> dict`, `save_send_state(state_path: Path, today: str, sent_count: int) -> None`
  - `run(dashboard_dir, summarized_path, state_path, today, dashboard_url, subscribers=None) -> dict` — 오케스트레이션. 반환 `{"sent": int, "failed": int, "skipped": bool}`. **어떤 예외도 밖으로 던지지 않는다**(내부 흡수·로그).

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import patch


def _seed(tmp_path):
    dash = tmp_path / "dashboard"; dash.mkdir()
    (dash / "2026-07-11.html").write_text(
        '<html><head><link rel="stylesheet" href="style.css"></head><body>x</body></html>',
        encoding="utf-8")
    summ = tmp_path / "summarized" / "2026-07-11.json"
    summ.parent.mkdir(parents=True, exist_ok=True)
    summ.write_text(json.dumps([{"id": "a1", "title": "T", "url": "https://e.com/1",
        "source": "디일렉", "summary": "s", "confirmation_tag": "[확정]",
        "summary_fallback": False, "category": ["메모리"], "tier": "핵심"}],
        ensure_ascii=False), encoding="utf-8")
    return dash, summ, tmp_path / "state" / "newsletter_state.json"


def test_run_sends_to_each_subscriber_and_records_state(tmp_path):
    dash, summ, state = _seed(tmp_path)
    with patch("src.step7_subscriber_email._send_html_email") as send:
        result = news.run(dash, summ, state, "2026-07-11", "https://site/",
                          subscribers=["a@x.com", "b@y.com"])
    assert send.call_count == 2
    assert result == {"sent": 2, "failed": 0, "skipped": False}
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["last_sent_date"] == "2026-07-11"
    assert saved["sent_count"] == 2


def test_run_skips_when_already_sent_today(tmp_path):
    dash, summ, state = _seed(tmp_path)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"last_sent_date": "2026-07-11", "sent_count": 2}),
                     encoding="utf-8")
    with patch("src.step7_subscriber_email._send_html_email") as send:
        result = news.run(dash, summ, state, "2026-07-11", "https://site/",
                          subscribers=["a@x.com"])
    send.assert_not_called()
    assert result["skipped"] is True


def test_run_force_resend_overrides_guard(tmp_path, monkeypatch):
    dash, summ, state = _seed(tmp_path)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"last_sent_date": "2026-07-11", "sent_count": 1}),
                     encoding="utf-8")
    monkeypatch.setenv("FORCE_RESEND", "true")
    with patch("src.step7_subscriber_email._send_html_email") as send:
        result = news.run(dash, summ, state, "2026-07-11", "https://site/",
                          subscribers=["a@x.com"])
    assert send.call_count == 1
    assert result["skipped"] is False


def test_run_empty_list_sends_nothing(tmp_path):
    dash, summ, state = _seed(tmp_path)
    with patch("src.step7_subscriber_email._send_html_email") as send:
        result = news.run(dash, summ, state, "2026-07-11", "https://site/", subscribers=[])
    send.assert_not_called()
    assert result == {"sent": 0, "failed": 0, "skipped": False}


def test_run_per_recipient_failure_continues_and_counts(tmp_path):
    dash, summ, state = _seed(tmp_path)

    def flaky(to_addr, *a, **k):
        if to_addr == "bad@x.com":
            raise OSError("smtp down")

    with patch("src.step7_subscriber_email._send_html_email", side_effect=flaky):
        result = news.run(dash, summ, state, "2026-07-11", "https://site/",
                          subscribers=["good@x.com", "bad@x.com"])
    assert result == {"sent": 1, "failed": 1, "skipped": False}


def test_run_never_raises_on_unexpected_error(tmp_path):
    # summarized/dashboard가 아예 없어도 예외를 밖으로 던지지 않는다.
    state = tmp_path / "state" / "newsletter_state.json"
    with patch("src.step7_subscriber_email._send_html_email"):
        result = news.run(tmp_path / "nope", tmp_path / "nope.json", state,
                          "2026-07-11", "https://site/", subscribers=["a@x.com"])
    assert "skipped" in result  # 예외 없이 dict 반환
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_step7_subscriber_email.py -k "test_run_" -q`
Expected: FAIL (`AttributeError: run` / `_send_html_email`)

- [ ] **Step 3: Write minimal implementation**

파일 상단 import에 다음을 추가한다:

```python
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
```

그리고 함수들 추가:

```python
def _send_html_email(
    to_addr: str, subject: str, html_body: str, attachment_name: str, attachment_html: str
) -> None:
    """HTML 본문 + HTML 첨부 1개를 SMTP로 발송한다. 실패 시 예외를 던진다."""
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    if not all([host, user, password]):
        raise RuntimeError("SMTP 설정(SMTP_HOST/USER/PASSWORD)이 없습니다")

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", _charset="utf-8"))

    attachment = MIMEText(attachment_html, "html", _charset="utf-8")
    attachment.add_header("Content-Disposition", "attachment", filename=attachment_name)
    msg.attach(attachment)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


def load_send_state(state_path: Path) -> dict:
    path = Path(state_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save_send_state(state_path: Path, today: str, sent_count: int) -> None:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"last_sent_date": today, "sent_count": sent_count}, ensure_ascii=False),
        encoding="utf-8",
    )


def run(
    dashboard_dir,
    summarized_path,
    state_path,
    today: str,
    dashboard_url: str,
    subscribers: list[str] | None = None,
) -> dict:
    """Step 7 진입점. 명단 구독자에게 그날 브리핑을 발송한다. 예외를 밖으로 던지지 않는다.

    Returns:
        {"sent": 성공 건수, "failed": 실패 건수, "skipped": 이번에 발송을 건너뛰었는지}
    """
    result = {"sent": 0, "failed": 0, "skipped": False}
    try:
        force = os.environ.get("FORCE_RESEND", "").strip().lower() == "true"
        if not force and load_send_state(state_path).get("last_sent_date") == today:
            logger.info("오늘(%s) 이미 발송함, 스킵", today)
            result["skipped"] = True
            return result

        if subscribers is None:
            subscribers = load_subscribers()
        if not subscribers:
            logger.info("구독자 명단이 비어 있어 발송하지 않습니다")
            return result

        subject = f"[반도체 브리핑] {today} 오늘의 핵심"
        body = build_email_body(Path(summarized_path), today, dashboard_url)
        attachment_html = build_standalone_html(Path(dashboard_dir), today)
        attachment_name = f"반도체브리핑_{today}.html"

        for addr in subscribers:
            try:
                _send_html_email(addr, subject, body, attachment_name, attachment_html)
                result["sent"] += 1
            except Exception as exc:  # noqa: BLE001 - 건별 실패는 로그 후 계속
                logger.error("구독자 %s 발송 실패: %s", addr, exc)
                result["failed"] += 1

        if result["sent"] > 0:
            save_send_state(state_path, today, result["sent"])
    except Exception as exc:  # noqa: BLE001 - Step 7 실패가 파이프라인을 막지 않도록 흡수
        logger.error("뉴스레터 발송 중 예기치 못한 오류(무시하고 계속): %s", exc)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_step7_subscriber_email.py -q`
Expected: PASS (전체)

- [ ] **Step 5: Commit**

```bash
git add src/step7_subscriber_email.py tests/test_step7_subscriber_email.py
git commit -m "feat: Step 7 발송 오케스트레이션 run + SMTP HTML 첨부 발송"
```

---

## Task 5: main.py 연동 `_maybe_send_newsletter`

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py` (없으면 Create)

**Interfaces:**
- Consumes: `src.step7_subscriber_email.run`, `paths`(dashboard_dir·summarized·state 경로), `today`
- Produces: `main._maybe_send_newsletter(base_dir, paths, today) -> None` — Step 7을 호출하되 예외를 흡수한다(로그만). Step 6 성공 직후 호출된다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main.py  (파일이 이미 있으면 이 테스트만 추가)
from pathlib import Path
from unittest.mock import patch

import main


def _paths(tmp_path):
    return {
        "dashboard_dir": tmp_path / "dashboard",
        "summarized": tmp_path / "summarized" / "2026-07-11.json",
        "state": tmp_path / "state" / "run_status.json",
    }


def test_maybe_send_newsletter_calls_step7(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_URL", "https://site.example/")
    with patch("main.step7_subscriber_email.run") as run:
        main._maybe_send_newsletter(tmp_path, _paths(tmp_path), "2026-07-11")
    run.assert_called_once()
    # dashboard_url이 환경변수에서 전달되는지 확인
    assert run.call_args.kwargs.get("dashboard_url") == "https://site.example/" \
        or "https://site.example/" in run.call_args.args


def test_maybe_send_newsletter_swallows_exceptions(tmp_path):
    with patch("main.step7_subscriber_email.run", side_effect=RuntimeError("boom")):
        # 예외가 밖으로 나오면 테스트 실패
        main._maybe_send_newsletter(tmp_path, _paths(tmp_path), "2026-07-11")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_main.py -q`
Expected: FAIL (`AttributeError: module 'main' has no attribute '_maybe_send_newsletter'` 또는 import 오류)

- [ ] **Step 3: Write minimal implementation**

`main.py` 상단 import 목록에 추가:

```python
from src import step7_subscriber_email
```

`main.py`에 헬퍼 함수 추가 (다른 `_maybe_*` 헬퍼 근처, 예: `_maybe_run_weekly_radar` 아래):

```python
_DEFAULT_DASHBOARD_URL = "https://fingerb9-blip.github.io/project/"


def _maybe_send_newsletter(base_dir, paths, today: str) -> None:
    """Step 6 성공 후 구독자에게 뉴스레터를 발송한다. 실패해도 파이프라인에 영향 없음."""
    try:
        dashboard_url = os.environ.get("DASHBOARD_URL", _DEFAULT_DASHBOARD_URL)
        summarized_path = base_dir / "data" / "summarized" / f"{today}.json"
        state_path = base_dir / "data" / "state" / "newsletter_state.json"
        result = step7_subscriber_email.run(
            paths["dashboard_dir"], summarized_path, state_path, today, dashboard_url
        )
        print(f"[NEWSLETTER] {result}")
    except Exception as exc:  # noqa: BLE001 - 발송 실패가 파이프라인을 막지 않도록 흡수
        print(f"[NEWSLETTER] 발송 래퍼 오류(무시): {exc}")
```

`main.py`에 `os` import가 없으면 상단에 `import os`도 추가한다.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_main.py -q`
Expected: PASS (2개)

- [ ] **Step 5: Step 6 성공 직후 호출 배선**

`main.py`의 성공 경로(run_status를 success로 저장하는 블록 이후, `try/except` 블록 밖)에서 호출을 추가한다. `run_status.save_status(..., "success" ...)` 저장 다음 줄에:

```python
    _maybe_send_newsletter(base_dir, paths, today)
```

(Step 6 실패 시에는 `try` 블록에서 예외가 발생해 이 지점에 도달하지 않으므로, 자동으로 "Step 6 성공 시에만 발송" 조건이 충족된다.)

- [ ] **Step 6: Run full suite to verify no regression**

Run: `python -m pytest -q`
Expected: PASS (전체)

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: main에 Step 7 뉴스레터 발송 연동(_maybe_send_newsletter, 성공 시에만)"
```

---

## Task 6: GitHub Actions 워크플로 env + 시크릿 안내

**Files:**
- Modify: `.github/workflows/daily_briefing.yml`

**Interfaces:**
- Consumes: GitHub Actions Secret `SUBSCRIBERS`, (선택) Variable/Secret `DASHBOARD_URL`
- Produces: `Run pipeline` 스텝이 `SUBSCRIBERS`/`DASHBOARD_URL` 환경변수를 파이프라인에 전달

- [ ] **Step 1: 워크플로 env 추가**

`.github/workflows/daily_briefing.yml`의 `Run pipeline` 스텝 `env:` 블록에 다음 두 줄을 추가한다 (기존 `NAVER_CLIENT_SECRET` 등과 같은 들여쓰기):

```yaml
          SUBSCRIBERS: ${{ secrets.SUBSCRIBERS }}
          DASHBOARD_URL: ${{ vars.DASHBOARD_URL || 'https://fingerb9-blip.github.io/project/' }}
```

- [ ] **Step 2: YAML 유효성 확인**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily_briefing.yml', encoding='utf-8')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: 시크릿 등록 안내 (수동, 사용자 작업)**

다음을 사용자에게 안내한다 (코드 아님):
- GitHub 저장소 → Settings → Secrets and variables → Actions → **New repository secret**
- Name: `SUBSCRIBERS`, Value: 수신 동의한 이메일을 콤마로 구분 (예: `a@x.com,b@y.com`)
- 로컬 테스트 시에는 `.env`에 `SUBSCRIBERS=...` 추가 (`.env`는 gitignore됨 — 커밋 금지)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/daily_briefing.yml
git commit -m "ci: daily-briefing에 SUBSCRIBERS/DASHBOARD_URL env 전달"
```

---

## Self-Review (작성자 확인 완료)

- **스펙 커버리지:** 명단 로드(T1)·자립형 HTML(T2)·본문 상위3(T3)·개별발송/중복가드/상태(T4)·main 성공시연동(T5)·시크릿 주입(T6) — 스펙 3~7장 전 항목 매핑됨.
- **플레이스홀더:** 없음(모든 스텝에 실제 코드/명령/기대값 포함).
- **타입 일관성:** `run(...)` 반환 `{"sent","failed","skipped"}`가 T4 테스트·T5 연동에서 동일하게 사용됨. `_send_html_email(to_addr, subject, html_body, attachment_name, attachment_html)` 시그니처가 T4 정의·mock·호출부에서 일치. `build_email_body`/`build_standalone_html` 인자·반환이 T2·T3·T4에서 일관.
- **범위:** 단일 구현 계획으로 적정(하위 시스템 분해 불필요).
