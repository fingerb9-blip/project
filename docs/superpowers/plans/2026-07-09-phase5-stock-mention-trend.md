# Phase 5 — 국내 주가 연동 + 언급량 트렌드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docs/phase5_ipo.md` 스펙대로 (A) 국내 관심 종목 주가를 뉴스 카드에 연동하고, (B) 기업
언급량과 (C) 기술 키워드 언급량 트렌드를 대시보드에 추가한다.

**Architecture:** 두 개의 독립 신규 모듈을 Step 4(요약) 이후 ~ Step 5(조립) 이전에 끼워 넣는다.
`src/step_stock_price.py`는 pykrx로 관심 종목의 당일 종가·등락률을 조회해 저장하고, 기사
제목/본문에 종목명이 언급되면 `related_stock` 필드를 붙인다. `src/step_mention_trend.py`는
이미 존재하는 기사의 `companies` 필드(Step 2가 `company_aliases.yaml`로 이미 채워둔 값)와
`tech_keywords.yaml` 기반 문자열 매칭으로 기업/키워드 언급 건수를 세고, 최근 7일 이동평균
대비 급증 여부를 판정한다. 두 모듈 모두 Gemini를 호출하지 않는다(기계적 집계라 기존
`company_aliases.yaml`/`keyword_hints`와 동일한 문자열 매칭 패턴을 재사용). `step5_assemble.py`는
`related_stock`이 있는 기사 카드에 주가 뱃지를, index.html에 언급량 트렌드 섹션을 추가한다.
14일 미만 데이터 누적 시 두 UI 모두 숨기고, 14~21일은 "(참고용)" 라벨을 붙인다.

**Tech Stack:** Python 3.11, pytest, PyYAML, `pykrx`(신규, KRX 시세 스크래핑, API 키 불필요),
`pandas`(pykrx 의존성으로 함께 설치됨) — 그 외 기존 스택(Gemini 미사용) 그대로.

## Global Constraints

- **기존 `companies` 필드 재사용**: `step2_dedup.normalize_company_names()`가 이미 모든 기사에
  `companies: list[str]`(정규화된 기업 id)를 채워둔다. `radar_weekly.py`·`step1_5_anomaly_detect.py`·
  `step4_5_issue_match.py`가 이 필드를 공유해 쓰고 있다. **문서의 `config/companies.yaml` +
  Gemini `companies` 필드 재추출(섹션 2)은 구현하지 않는다** — 같은 이름의 필드를 두 가지
  방식으로 채우면 충돌한다. 기업 언급량 트렌드(기능 B)는 이 기존 필드를 그대로 집계한다.
  (사용자 확인 완료.)
- **`step3_classify.py`는 이 Phase에서 변경하지 않는다** — 위 결정에 따라 Gemini 분류
  프롬프트/스키마 확장이 필요 없다.
- **주가 매칭은 `companies` 필드를 거치지 않고 직접 문자열 매칭**: `config/watch_tickers.yaml`의
  종목명을 기사 제목+본문에서 직접 찾는다(기존 `company_aliases.yaml`에 DB하이텍·한미반도체가
  없어도 즉시 동작하도록). 이는 문서 1장의 "companies 필드 기준 매칭" 서술과 다르지만, 기존
  `filter_by_keywords`의 화이트리스트 매칭과 동일한 패턴이라 코드베이스 일관성이 더 높다.
- **`data/trends/YYYY-MM-DD.json`로 날짜별 저장** (문서의 단일 경로 `data/trends/mention_trend.json`
  대신) — 이동평균 계산에 과거 날짜 파일을 다시 읽어야 하므로, `data/raw`·`data/dedup` 등과
  동일한 날짜별 파일 패턴을 따른다. `data/stock/YYYY-MM-DD.json`은 문서에 이미 날짜별 경로로
  명시돼 있어 그대로 따른다.
- **차트는 순수 CSS 바(bar)로 렌더링** — `build_radar_section_html()`(Phase 4)이 이미 이
  패턴(막대 너비 %)으로 구현돼 있고, matplotlib 등 추가 라이브러리나 클라이언트 JS 차트
  라이브러리를 새로 들이지 않는다. 문서의 "라인 차트"·"종목 상세 뷰"(다중 페이지)는 이번
  범위에서 구현하지 않는다 — 기사 카드 뱃지 + index.html 요약 바 차트로 대체한다.
  대시보드 생성 코드는 기사 데이터·통계만 사용하며 환경변수/Secrets를 참조하지 않고,
  외부 소스 텍스트는 모두 `_esc()`로 이스케이프한다(CLAUDE.md 기존 원칙, Step 5 전체에 적용).
- **콜드 스타트**: `count_accumulated_days()` 기준 14일 미만이면 두 기능 모두 대시보드에서
  완전히 숨긴다(주가 뱃지 미부착, 트렌드 섹션 미출력). 14~21일은 표시하되 트렌드 섹션 제목에
  "(참고용)"을 붙인다. 21일 이후 라벨 없이 정상 표시한다.
- pykrx 조회 실패 시 직전 날짜의 저장값을 유지하고(알림 없음), 파이프라인은 계속 진행한다
  (기존 Step 4 요약 실패 폴백과 동일한 "계속 진행" 원칙).

---

### Task 1: 설정 파일 + 의존성 준비

**Files:**
- Create: `config/watch_tickers.yaml`
- Create: `config/tech_keywords.yaml`
- Modify: `requirements.txt`
- Test: `tests/test_config_data.py` (신규 파일)

**Interfaces:**
- Consumes: 없음
- Produces: `config/watch_tickers.yaml`의 `tickers: [{name, ticker}]` 리스트,
  `config/tech_keywords.yaml`의 `keywords: [{canonical, aliases}]` 리스트 — Task 2(주가),
  Task 4(언급량)가 이 구조를 그대로 소비한다. `pykrx==1.2.8`이 설치되어 이후 태스크에서
  `from pykrx import stock`이 동작한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_config_data.py` 파일을 새로 만든다:

```python
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(relative_path: str) -> dict:
    with (_ROOT / relative_path).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_watch_tickers_yaml_has_domestic_tickers():
    data = _load_yaml("config/watch_tickers.yaml")

    names = [t["name"] for t in data["tickers"]]
    assert "삼성전자" in names
    assert "SK하이닉스" in names
    tickers = {t["name"]: t["ticker"] for t in data["tickers"]}
    assert tickers["삼성전자"] == "005930"


def test_tech_keywords_yaml_has_canonical_and_aliases():
    data = _load_yaml("config/tech_keywords.yaml")

    by_canonical = {k["canonical"]: k["aliases"] for k in data["keywords"]}
    assert "HBM4" in by_canonical["HBM"]
    assert "EUV" in by_canonical
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python -m pytest tests/test_config_data.py -v`
Expected: FAIL — `config/watch_tickers.yaml`, `config/tech_keywords.yaml` 파일이 아직
없어 `FileNotFoundError`.

- [ ] **Step 3: `config/watch_tickers.yaml` 작성**

```yaml
tickers:
  - name: "삼성전자"
    ticker: "005930"
  - name: "SK하이닉스"
    ticker: "000660"
  - name: "DB하이텍"
    ticker: "000990"
  - name: "한미반도체"
    ticker: "042700"
```

- [ ] **Step 4: `config/tech_keywords.yaml` 작성**

```yaml
keywords:
  - canonical: "HBM"
    aliases: ["고대역폭메모리", "HBM3", "HBM3E", "HBM4"]
  - canonical: "EUV"
    aliases: ["극자외선", "EUV 노광"]
  - canonical: "첨단 패키징"
    aliases: ["CoWoS", "2.5D 패키징", "칩렛"]
  - canonical: "2나노 공정"
    aliases: ["2nm", "GAA"]
```

- [ ] **Step 5: `requirements.txt`에 pykrx 추가**

`requirements.txt` 끝에 추가:

```
pykrx==1.2.8
```

- [ ] **Step 6: pykrx 설치 + 테스트 통과 확인**

Run: `pip install pykrx==1.2.8`
Run: `python -m pytest tests/test_config_data.py -v`
Expected: PASS (2 passed). `python -c "from pykrx import stock"`도 에러 없이 실행돼야 한다
(Task 2가 이 임포트에 의존한다).

- [ ] **Step 7: 커밋**

```bash
git add config/watch_tickers.yaml config/tech_keywords.yaml requirements.txt tests/test_config_data.py
git commit -m "feat: add Phase 5 config (watch tickers, tech keywords) and pykrx dependency"
```

---

### Task 2: `step_stock_price.py` — 국내 주가 조회 + 저장

**Files:**
- Create: `src/step_stock_price.py`
- Test: `tests/test_step_stock_price.py` (신규 파일)

**Interfaces:**
- Consumes: `pykrx.stock.get_market_ohlcv_by_date(fromdate, todate, ticker) -> pandas.DataFrame`
  (컬럼에 `종가`, `등락률` 포함, 최신 거래일이 마지막 행)
- Produces: `load_watch_tickers(path) -> list[dict]`, `run(watch_tickers, output_path, today) -> dict`
  (`{"date": str, "tickers": [{"ticker","name","close","change_pct"}]}`, 반환값과 동일한
  내용을 `output_path`에도 저장). Task 3이 `run()`의 반환값(`stock_data`)을 소비한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_step_stock_price.py` 파일을 새로 만든다:

```python
import json

import pandas as pd

from src import step_stock_price


def test_load_watch_tickers_reads_yaml(tmp_path):
    path = tmp_path / "watch_tickers.yaml"
    path.write_text('tickers:\n  - name: "삼성전자"\n    ticker: "005930"\n', encoding="utf-8")

    tickers = step_stock_price.load_watch_tickers(path)

    assert tickers == [{"name": "삼성전자", "ticker": "005930"}]


def test_fetch_ticker_ohlcv_returns_latest_close_and_change_pct(monkeypatch):
    df = pd.DataFrame({"종가": [90000, 92300], "등락률": [-0.5, 1.8]})
    monkeypatch.setattr(step_stock_price.stock, "get_market_ohlcv_by_date", lambda *a, **k: df)

    result = step_stock_price.fetch_ticker_ohlcv("005930", "2026-07-09")

    assert result == (92300.0, 1.8)


def test_fetch_ticker_ohlcv_returns_none_for_empty_dataframe(monkeypatch):
    monkeypatch.setattr(step_stock_price.stock, "get_market_ohlcv_by_date", lambda *a, **k: pd.DataFrame())

    result = step_stock_price.fetch_ticker_ohlcv("005930", "2026-07-09")

    assert result is None


def test_run_writes_output_and_returns_tickers(tmp_path, monkeypatch):
    df = pd.DataFrame({"종가": [92300], "등락률": [1.8]})
    monkeypatch.setattr(step_stock_price.stock, "get_market_ohlcv_by_date", lambda *a, **k: df)
    watch_tickers = [{"name": "삼성전자", "ticker": "005930"}]
    output_path = tmp_path / "stock" / "2026-07-09.json"

    result = step_stock_price.run(watch_tickers, str(output_path), "2026-07-09")

    assert result["tickers"] == [
        {"ticker": "005930", "name": "삼성전자", "close": 92300.0, "change_pct": 1.8}
    ]
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == result


def test_run_falls_back_to_previous_day_on_fetch_failure(tmp_path, monkeypatch):
    stock_dir = tmp_path / "stock"
    stock_dir.mkdir()
    previous = {
        "date": "2026-07-08",
        "tickers": [{"ticker": "005930", "name": "삼성전자", "close": 90000.0, "change_pct": -0.5}],
    }
    (stock_dir / "2026-07-08.json").write_text(json.dumps(previous), encoding="utf-8")

    def _raise(*a, **k):
        raise RuntimeError("network error")

    monkeypatch.setattr(step_stock_price.stock, "get_market_ohlcv_by_date", _raise)
    watch_tickers = [{"name": "삼성전자", "ticker": "005930"}]
    output_path = stock_dir / "2026-07-09.json"

    result = step_stock_price.run(watch_tickers, str(output_path), "2026-07-09")

    assert result["tickers"] == previous["tickers"]
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python -m pytest tests/test_step_stock_price.py -v`
Expected: FAIL — `src/step_stock_price.py` 모듈이 아직 없어 `ModuleNotFoundError`.

- [ ] **Step 3: `src/step_stock_price.py` 작성**

```python
"""Phase 5. 국내 주가 연동 — pykrx로 관심 종목 종가·등락률 조회."""

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import yaml
from pykrx import stock

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 10


def load_watch_tickers(path) -> list[dict]:
    """config/watch_tickers.yaml을 읽어 관심 종목 목록을 반환한다.

    Args:
        path: config/watch_tickers.yaml 경로

    Returns:
        [{"name": str, "ticker": str}] 리스트
    """
    with Path(path).open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("tickers", [])


def fetch_ticker_ohlcv(ticker: str, today: str) -> tuple[float, float] | None:
    """지정 종목의 today 기준 가장 최근 거래일 종가·등락률을 조회한다.

    휴장일(주말·공휴일)을 감안해 today 기준 최근 _LOOKBACK_DAYS일을 조회 범위로 잡고,
    조회된 마지막 행(가장 최근 거래일)을 사용한다.

    Args:
        ticker: 6자리 종목코드
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        (종가, 등락률) 튜플, 조회 결과가 없으면 None
    """
    to_date = today.replace("-", "")
    from_date = (date.fromisoformat(today) - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d")
    df = stock.get_market_ohlcv_by_date(from_date, to_date, ticker)
    if df.empty:
        return None
    last_row = df.iloc[-1]
    return float(last_row["종가"]), float(last_row["등락률"])


def _load_previous_tickers(stock_dir: Path, today: str) -> list[dict]:
    """today 이전 날짜의 가장 최근 저장 파일에서 tickers 리스트를 읽는다. 없으면 빈 리스트."""
    if not stock_dir.exists():
        return []
    files = sorted(p for p in stock_dir.glob("*.json") if p.stem < today)
    if not files:
        return []
    with files[-1].open(encoding="utf-8") as f:
        return json.load(f).get("tickers", [])


def run(watch_tickers: list[dict], output_path: str, today: str) -> dict:
    """신규 Step. 관심 종목의 당일 종가·등락률을 조회해 저장한다.

    조회 실패(예외 발생 또는 빈 결과) 시 직전 저장값을 유지한다. 직전 값도 없으면
    해당 종목은 결과에서 제외한다 (알림 없이 조용히 처리, 파이프라인은 계속 진행).

    Args:
        watch_tickers: load_watch_tickers() 결과
        output_path: data/stock/YYYY-MM-DD.json 저장 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        {"date": str, "tickers": [{"ticker","name","close","change_pct"}]}
    """
    output_path = Path(output_path)
    previous_tickers = _load_previous_tickers(output_path.parent, today)

    tickers_out = []
    for entry in watch_tickers:
        name, ticker = entry["name"], entry["ticker"]
        try:
            result = fetch_ticker_ohlcv(ticker, today)
        except Exception as exc:  # noqa: BLE001 - 조회 실패 시 직전 값으로 폴백
            logger.warning("%s(%s) 주가 조회 실패, 직전 값 유지: %s", name, ticker, exc)
            result = None

        if result is None:
            prev_entry = next((t for t in previous_tickers if t["ticker"] == ticker), None)
            if prev_entry is not None:
                tickers_out.append(prev_entry)
            continue

        close, change_pct = result
        tickers_out.append({"ticker": ticker, "name": name, "close": close, "change_pct": change_pct})

    data = {"date": today, "tickers": tickers_out}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `python -m pytest tests/test_step_stock_price.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/step_stock_price.py tests/test_step_stock_price.py
git commit -m "feat: fetch domestic watch-ticker prices via pykrx with previous-day fallback"
```

---

### Task 3: `step_stock_price.py` — 기사 카드에 관련 종목 등락률 연결

**Files:**
- Modify: `src/step_stock_price.py`
- Test: `tests/test_step_stock_price.py`

**Interfaces:**
- Consumes: Task 2의 `run()` 반환값(`stock_data: dict`)
- Produces: `match_articles_to_stocks(articles, stock_data) -> list[dict]` — 각 기사 dict에
  `related_stock: [{"name": str, "change_pct": float}]` 필드를 추가한다(매칭 없으면 빈 리스트).
  Task 6이 이 필드를 읽어 카드에 뱃지로 렌더링한다. Task 8이 이 함수를 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_step_stock_price.py` 파일 끝에 추가:

```python
def test_match_articles_to_stocks_adds_related_stock_when_name_mentioned():
    stock_data = {
        "date": "2026-07-09",
        "tickers": [{"ticker": "005930", "name": "삼성전자", "close": 92300.0, "change_pct": 1.8}],
    }
    articles = [{"id": "a1", "title": "삼성전자, HBM4 수율 개선 발표", "raw_text": ""}]

    result = step_stock_price.match_articles_to_stocks(articles, stock_data)

    assert result[0]["related_stock"] == [{"name": "삼성전자", "change_pct": 1.8}]


def test_match_articles_to_stocks_leaves_empty_list_when_no_ticker_mentioned():
    stock_data = {
        "date": "2026-07-09",
        "tickers": [{"ticker": "005930", "name": "삼성전자", "close": 92300.0, "change_pct": 1.8}],
    }
    articles = [{"id": "a1", "title": "TSMC, 2나노 공정 수율 개선", "raw_text": ""}]

    result = step_stock_price.match_articles_to_stocks(articles, stock_data)

    assert result[0]["related_stock"] == []
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python -m pytest tests/test_step_stock_price.py -v`
Expected: FAIL — `match_articles_to_stocks`가 아직 없어 `AttributeError`.

- [ ] **Step 3: `match_articles_to_stocks` 추가**

`src/step_stock_price.py` 파일 끝에 추가:

```python
def match_articles_to_stocks(articles: list[dict], stock_data: dict) -> list[dict]:
    """기사 제목/본문에 언급된 관심 종목의 당일 등락률을 related_stock 필드로 붙인다.

    Args:
        articles: 기사 dict 리스트 (title, raw_text 포함)
        stock_data: run() 결과 ({"date", "tickers": [...]})

    Returns:
        각 기사에 related_stock: [{"name","change_pct"}] 필드가 추가된 동일 리스트
    """
    tickers = stock_data.get("tickers", [])
    for article in articles:
        text = f"{article['title']} {article.get('raw_text', '')}"
        article["related_stock"] = [
            {"name": t["name"], "change_pct": t["change_pct"]} for t in tickers if t["name"] in text
        ]
    return articles
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `python -m pytest tests/test_step_stock_price.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/step_stock_price.py tests/test_step_stock_price.py
git commit -m "feat: attach related watch-ticker change_pct to articles mentioning them"
```

---

### Task 4: `step_mention_trend.py` — 기업/키워드 언급량 집계 + 급증 판정

**Files:**
- Create: `src/step_mention_trend.py`
- Test: `tests/test_step_mention_trend.py` (신규 파일)

**Interfaces:**
- Consumes: `issue_tracking.entity_display_name(entity_id, aliases_config) -> str` (기존 함수,
  `src/issue_tracking.py`), 기사 dict의 기존 `companies: list[str]` 필드
- Produces: `load_tech_keywords(path) -> list[dict]`,
  `run(classified_articles, aliases_config, tech_keywords, trends_dir, today) -> dict`
  (`{"date": str, "companies": [{"name","count","is_spike"}], "keywords": [...]}`, 동일 내용을
  `trends_dir/today.json`에도 저장). Task 5가 이 파일에 `count_accumulated_days`/
  `cold_start_stage`를 추가한다. Task 7이 `run()`의 반환값(`trend_data`)을 소비한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_step_mention_trend.py` 파일을 새로 만든다:

```python
import json

from src import step_mention_trend

_ALIASES = {
    "samsung_electronics": {"aliases": ["삼성전자"], "segment": ["메모리"]},
    "sk_hynix": {"aliases": ["SK하이닉스"], "segment": ["메모리"]},
}

_TECH_KEYWORDS = [
    {"canonical": "HBM", "aliases": ["HBM3", "HBM4"]},
    {"canonical": "EUV", "aliases": ["극자외선"]},
]


def test_load_tech_keywords_reads_yaml(tmp_path):
    path = tmp_path / "tech_keywords.yaml"
    path.write_text('keywords:\n  - canonical: "HBM"\n    aliases: ["HBM4"]\n', encoding="utf-8")

    keywords = step_mention_trend.load_tech_keywords(path)

    assert keywords == [{"canonical": "HBM", "aliases": ["HBM4"]}]


def test_count_company_mentions_uses_display_name():
    articles = [
        {"companies": ["samsung_electronics"]},
        {"companies": ["samsung_electronics", "sk_hynix"]},
    ]

    counts = step_mention_trend.count_company_mentions(articles, _ALIASES)

    assert counts == {"삼성전자": 2, "SK하이닉스": 1}


def test_match_tech_keywords_matches_alias_not_just_canonical():
    matched = step_mention_trend.match_tech_keywords("삼성전자, HBM4 공급 확대", _TECH_KEYWORDS)

    assert matched == ["HBM"]


def test_count_keyword_mentions_counts_title_and_raw_text():
    articles = [
        {"title": "HBM4 수율 개선", "raw_text": ""},
        {"title": "EUV 노광 장비 도입", "raw_text": "극자외선 공정 확대"},
    ]

    counts = step_mention_trend.count_keyword_mentions(articles, _TECH_KEYWORDS)

    assert counts == {"HBM": 1, "EUV": 1}


def test_run_flags_spike_when_count_far_above_moving_average(tmp_path):
    trends_dir = tmp_path / "trends"
    trends_dir.mkdir()
    for days_ago in range(1, 8):
        day = f"2026-07-{9 - days_ago:02d}"
        (trends_dir / f"{day}.json").write_text(
            json.dumps({"date": day, "companies": [{"name": "삼성전자", "count": 1, "is_spike": False}], "keywords": []}),
            encoding="utf-8",
        )
    articles = [{"companies": ["samsung_electronics"], "title": "", "raw_text": ""} for _ in range(5)]

    result = step_mention_trend.run(articles, _ALIASES, _TECH_KEYWORDS, str(trends_dir), "2026-07-09")

    assert result["companies"] == [{"name": "삼성전자", "count": 5, "is_spike": True}]
    saved = json.loads((trends_dir / "2026-07-09.json").read_text(encoding="utf-8"))
    assert saved == result


def test_run_does_not_flag_spike_on_cold_start_with_low_count(tmp_path):
    trends_dir = tmp_path / "trends"
    articles = [{"companies": ["samsung_electronics"], "title": "", "raw_text": ""}]

    result = step_mention_trend.run(articles, _ALIASES, _TECH_KEYWORDS, str(trends_dir), "2026-07-09")

    assert result["companies"] == [{"name": "삼성전자", "count": 1, "is_spike": False}]
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python -m pytest tests/test_step_mention_trend.py -v`
Expected: FAIL — `src/step_mention_trend.py` 모듈이 아직 없어 `ModuleNotFoundError`.

- [ ] **Step 3: `src/step_mention_trend.py` 작성**

```python
"""Phase 5. 기업/기술 키워드 언급량 트렌드 — 이동평균 대비 급증 감지."""

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import yaml

from src import issue_tracking

logger = logging.getLogger(__name__)

_ROLLING_WINDOW_DAYS = 7
_SPIKE_RATIO = 2.0
_COLD_START_MIN_COUNT = 3


def load_tech_keywords(path) -> list[dict]:
    """config/tech_keywords.yaml을 읽어 기술 키워드 목록을 반환한다.

    Args:
        path: config/tech_keywords.yaml 경로

    Returns:
        [{"canonical": str, "aliases": list[str]}] 리스트
    """
    with Path(path).open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("keywords", [])


def count_company_mentions(articles: list[dict], aliases_config: dict) -> dict[str, int]:
    """기사의 companies 필드(Step 2가 이미 정규화)를 집계해 기업별 언급 건수를 센다.

    Args:
        articles: companies 필드가 포함된 기사 리스트
        aliases_config: config/company_aliases.yaml 로드 결과

    Returns:
        {표기명: 언급 건수} dict
    """
    counts: dict[str, int] = {}
    for article in articles:
        for company_id in article.get("companies") or []:
            name = issue_tracking.entity_display_name(company_id, aliases_config)
            counts[name] = counts.get(name, 0) + 1
    return counts


def match_tech_keywords(text: str, tech_keywords: list[dict]) -> list[str]:
    """텍스트에 언급된 기술 키워드의 canonical 이름 목록을 반환한다.

    Args:
        text: 검색 대상 텍스트
        tech_keywords: load_tech_keywords() 결과

    Returns:
        매칭된 canonical 이름 리스트 (중복 없음, 순서는 tech_keywords 순서)
    """
    matched = []
    for entry in tech_keywords:
        canonical = entry["canonical"]
        terms = [canonical, *entry.get("aliases", [])]
        if any(term in text for term in terms):
            matched.append(canonical)
    return matched


def count_keyword_mentions(articles: list[dict], tech_keywords: list[dict]) -> dict[str, int]:
    """기사 제목+본문에서 매칭되는 기술 키워드별 언급 건수를 센다.

    Args:
        articles: title, raw_text가 포함된 기사 리스트
        tech_keywords: load_tech_keywords() 결과

    Returns:
        {canonical 이름: 언급 건수} dict
    """
    counts: dict[str, int] = {}
    for article in articles:
        text = f"{article.get('title', '')} {article.get('raw_text', '')}"
        for name in match_tech_keywords(text, tech_keywords):
            counts[name] = counts.get(name, 0) + 1
    return counts


def _load_day_counts(trends_dir: Path, day: str, field: str) -> dict[str, int]:
    path = trends_dir / f"{day}.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {item["name"]: item["count"] for item in data.get(field, [])}


def _moving_average(trends_dir: Path, today: str, name: str, field: str) -> float:
    """오늘 이전 _ROLLING_WINDOW_DAYS일의 name 언급 건수 평균(데이터 없는 날은 0)."""
    counts = []
    for days_ago in range(1, _ROLLING_WINDOW_DAYS + 1):
        day = (date.fromisoformat(today) - timedelta(days=days_ago)).isoformat()
        counts.append(_load_day_counts(trends_dir, day, field).get(name, 0))
    return sum(counts) / len(counts) if counts else 0.0


def _build_trend_entries(counts: dict[str, int], trends_dir: Path, today: str, field: str) -> list[dict]:
    entries = []
    for name, count in counts.items():
        avg = _moving_average(trends_dir, today, name, field)
        is_spike = (count / avg >= _SPIKE_RATIO) if avg > 0 else (count >= _COLD_START_MIN_COUNT)
        entries.append({"name": name, "count": count, "is_spike": is_spike})
    return sorted(entries, key=lambda e: e["count"], reverse=True)


def run(
    classified_articles: list[dict],
    aliases_config: dict,
    tech_keywords: list[dict],
    trends_dir: str,
    today: str,
) -> dict:
    """신규 Step. 기업·기술 키워드 언급량을 집계하고 이동평균 대비 급증 여부를 판정한다.

    Args:
        classified_articles: data/classified/YYYY-MM-DD.json 로드 결과 (companies 필드 포함)
        aliases_config: config/company_aliases.yaml 로드 결과
        tech_keywords: load_tech_keywords() 결과
        trends_dir: data/trends 디렉토리 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        {"date","companies": [{"name","count","is_spike"}],"keywords": [...]}
        (trends_dir/{today}.json에도 저장)
    """
    trends_dir = Path(trends_dir)
    company_counts = count_company_mentions(classified_articles, aliases_config)
    keyword_counts = count_keyword_mentions(classified_articles, tech_keywords)

    data = {
        "date": today,
        "companies": _build_trend_entries(company_counts, trends_dir, today, "companies"),
        "keywords": _build_trend_entries(keyword_counts, trends_dir, today, "keywords"),
    }

    trends_dir.mkdir(parents=True, exist_ok=True)
    with (trends_dir / f"{today}.json").open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `python -m pytest tests/test_step_mention_trend.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/step_mention_trend.py tests/test_step_mention_trend.py
git commit -m "feat: aggregate company/tech-keyword mention counts with moving-average spike detection"
```

---

### Task 5: `step_mention_trend.py` — 콜드 스타트 단계 판정

**Files:**
- Modify: `src/step_mention_trend.py`
- Test: `tests/test_step_mention_trend.py`

**Interfaces:**
- Consumes: 없음 (순수 함수)
- Produces: `count_accumulated_days(trends_dir, today) -> int`,
  `cold_start_stage(accumulated_days: int) -> str` (반환값 `"hidden"|"preview"|"active"`).
  Task 8이 이 두 함수를 호출해 Task 3/7의 기능을 켤지 말지 결정한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_step_mention_trend.py` 파일 끝에 추가:

```python
def test_count_accumulated_days_counts_existing_files_plus_today(tmp_path):
    trends_dir = tmp_path / "trends"
    trends_dir.mkdir()
    (trends_dir / "2026-07-01.json").write_text("{}", encoding="utf-8")
    (trends_dir / "2026-07-02.json").write_text("{}", encoding="utf-8")

    days = step_mention_trend.count_accumulated_days(str(trends_dir), "2026-07-03")

    assert days == 3


def test_count_accumulated_days_returns_one_when_dir_missing(tmp_path):
    days = step_mention_trend.count_accumulated_days(str(tmp_path / "nope"), "2026-07-03")

    assert days == 1


def test_cold_start_stage_boundaries():
    assert step_mention_trend.cold_start_stage(13) == "hidden"
    assert step_mention_trend.cold_start_stage(14) == "preview"
    assert step_mention_trend.cold_start_stage(20) == "preview"
    assert step_mention_trend.cold_start_stage(21) == "active"
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python -m pytest tests/test_step_mention_trend.py -v`
Expected: FAIL — `count_accumulated_days`/`cold_start_stage`가 아직 없어 `AttributeError`.

- [ ] **Step 3: 두 함수 추가**

`src/step_mention_trend.py`의 모듈 상단 상수 블록에 추가:

```python
_HIDDEN_DAYS = 14
_PREVIEW_DAYS = 21
```

파일 끝에 추가:

```python
def count_accumulated_days(trends_dir: str, today: str) -> int:
    """data/trends/*.json 파일 수(오늘 포함) 기준으로 누적 운영 일수를 계산한다.

    Args:
        trends_dir: data/trends 디렉토리 경로
        today: YYYY-MM-DD 형식 날짜 문자열

    Returns:
        누적 운영 일수 (디렉토리가 없으면 1 — 오늘이 첫 실행)
    """
    trends_dir = Path(trends_dir)
    if not trends_dir.exists():
        return 1
    days = {p.stem for p in trends_dir.glob("*.json")}
    days.add(today)
    return len(days)


def cold_start_stage(accumulated_days: int) -> str:
    """콜드 스타트 단계를 판정한다.

    Args:
        accumulated_days: count_accumulated_days() 결과

    Returns:
        "hidden"(14일 미만) | "preview"(14~20일) | "active"(21일 이후)
    """
    if accumulated_days < _HIDDEN_DAYS:
        return "hidden"
    if accumulated_days < _PREVIEW_DAYS:
        return "preview"
    return "active"
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `python -m pytest tests/test_step_mention_trend.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/step_mention_trend.py tests/test_step_mention_trend.py
git commit -m "feat: gate mention-trend/stock UI behind a 14/21-day cold-start stage"
```

---

### Task 6: `step5_assemble.py` — 기사 카드에 주가 뱃지 렌더링

**Files:**
- Modify: `src/step5_assemble.py:282-349` (`_build_article_card`), `_DASHBOARD_CSS`
- Test: `tests/test_step5_assemble.py`

**Interfaces:**
- Consumes: 기사 dict의 `related_stock: [{"name","change_pct"}]` 필드 (Task 3이 채움)
- Produces: `_build_article_card()`가 `related_stock`이 있으면 종목별 등락률 뱃지를
  카드에 렌더링한다. 시그니처 변경 없음(같은 dict를 읽기만 함).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_step5_assemble.py`에서 기존 임포트·헬퍼를 확인한 뒤 파일 끝에 추가
(기존 파일에 이미 `from src import step5_assemble`가 있다는 전제):

```python
def test_build_article_card_renders_positive_stock_badge():
    article = {
        "id": "a1",
        "title": "삼성전자, HBM4 수율 개선",
        "url": "https://example.com/1",
        "source": "삼성전자 뉴스룸",
        "category": ["메모리"],
        "summary": "요약",
        "confirmation_tag": "[확정]",
        "related_stock": [{"name": "삼성전자", "change_pct": 1.8}],
    }

    html = step5_assemble._build_article_card(article)

    assert "stock-up" in html
    assert "삼성전자" in html
    assert "1.8%" in html


def test_build_article_card_renders_negative_stock_badge():
    article = {
        "id": "a1",
        "title": "삼성전자, HBM4 수율 개선",
        "url": "https://example.com/1",
        "source": "삼성전자 뉴스룸",
        "category": ["메모리"],
        "summary": "요약",
        "confirmation_tag": "[확정]",
        "related_stock": [{"name": "삼성전자", "change_pct": -2.3}],
    }

    html = step5_assemble._build_article_card(article)

    assert "stock-down" in html
    assert "2.3%" in html


def test_build_article_card_omits_stock_badge_when_no_related_stock():
    article = {
        "id": "a1",
        "title": "TSMC, 2나노 공정 발표",
        "url": "https://example.com/1",
        "source": "디일렉",
        "category": ["파운드리"],
        "summary": "요약",
        "confirmation_tag": "[관측]",
        "related_stock": [],
    }

    html = step5_assemble._build_article_card(article)

    assert "stock-up" not in html
    assert "stock-down" not in html
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k stock_badge -v`
Expected: FAIL — 현재 `_build_article_card`는 `related_stock`을 전혀 읽지 않으므로
`"stock-up"`/`"stock-down"`이 출력 HTML에 없어 `assert` 실패.

- [ ] **Step 3: `_build_article_card`에 주가 뱃지 렌더링 추가**

`src/step5_assemble.py`에서 다음 블록(카테고리 칩 렌더링 다음, `time_label` 계산 전):

```python
    for category in article_categories:
        parts.append(f'<span class="chip">{_esc(category)}</span>')
    time_label = _format_card_time(article.get("published_at"))
```

을 다음으로 교체한다:

```python
    for category in article_categories:
        parts.append(f'<span class="chip">{_esc(category)}</span>')
    for stock_entry in article.get("related_stock") or []:
        change_pct = stock_entry["change_pct"]
        direction_class = "stock-up" if change_pct >= 0 else "stock-down"
        arrow = "▲" if change_pct >= 0 else "▼"
        parts.append(
            f'<span class="chip {direction_class}">{_esc(stock_entry["name"])} '
            f'{arrow}{abs(change_pct):.1f}%</span>'
        )
    time_label = _format_card_time(article.get("published_at"))
```

- [ ] **Step 4: CSS 클래스 추가**

`src/step5_assemble.py`의 `_DASHBOARD_CSS` 문자열에서 다음 줄:

```
.chip{font-size:.74rem;color:var(--ink-soft);padding:3px 9px;border:1px solid var(--line);border-radius:999px}
```

다음 줄 바로 뒤에 추가:

```
.chip.stock-up{background:rgba(46,158,91,.12);color:var(--confirmed);border-color:transparent}
.chip.stock-down{background:rgba(194,59,59,.1);color:#C23B3B;border-color:transparent}
```

- [ ] **Step 5: 테스트 실행해 통과 확인**

Run: `python -m pytest tests/test_step5_assemble.py -v`
Expected: PASS (기존 테스트 전부 + 신규 3개)

- [ ] **Step 6: 커밋**

```bash
git add src/step5_assemble.py tests/test_step5_assemble.py
git commit -m "feat: render related-stock change_pct badges on article cards"
```

---

### Task 7: `step5_assemble.py` — 언급량 트렌드 섹션 (index.html)

**Files:**
- Modify: `src/step5_assemble.py` (`build_index_html`, `_DASHBOARD_CSS`)
- Test: `tests/test_step5_assemble.py`

**Interfaces:**
- Consumes: Task 4의 `trend_data`(`{"date","companies","keywords"}` — 각 항목
  `{"name","count","is_spike"}`), Task 5의 `cold_start_stage` 문자열
- Produces: `build_mention_trend_section_html(trend_data, stage) -> str` (신규 함수),
  `build_index_html(..., mention_trend_data: dict | None = None, cold_start_stage: str = "active")`
  — 기존 호출부(`scripts/rebuild_dashboard.py`, `step1_5_anomaly_detect.py`)는 새 파라미터를
  넘기지 않아도 되도록 둘 다 기본값을 가진다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_step5_assemble.py` 파일 끝에 추가:

```python
_TREND_DATA = {
    "date": "2026-07-09",
    "companies": [{"name": "삼성전자", "count": 5, "is_spike": True}],
    "keywords": [{"name": "HBM", "count": 3, "is_spike": False}],
}


def test_build_mention_trend_section_html_renders_bars_and_spike_chip():
    html = step5_assemble.build_mention_trend_section_html(_TREND_DATA, "active")

    assert "삼성전자" in html
    assert "HBM" in html
    assert "급증" in html


def test_build_mention_trend_section_html_adds_preview_label():
    html = step5_assemble.build_mention_trend_section_html(_TREND_DATA, "preview")

    assert "참고용" in html


def test_build_mention_trend_section_html_empty_when_no_data():
    assert step5_assemble.build_mention_trend_section_html(None, "active") == ""


def test_build_index_html_includes_mention_trend_section(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "state" / "run_status.json"

    html = step5_assemble.build_index_html(
        dashboard_dir, state_path, mention_trend_data=_TREND_DATA, cold_start_stage="active"
    )

    assert "삼성전자" in html


def test_build_index_html_omits_mention_trend_section_when_none(tmp_path):
    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir()
    state_path = tmp_path / "state" / "run_status.json"

    html = step5_assemble.build_index_html(dashboard_dir, state_path)

    assert "언급량 트렌드" not in html
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python -m pytest tests/test_step5_assemble.py -k mention_trend -v`
Expected: FAIL — `build_mention_trend_section_html`이 아직 없어 `AttributeError`, `build_index_html`은
`mention_trend_data`/`cold_start_stage` 키워드 인자를 받지 않아 `TypeError`.

- [ ] **Step 3: `build_mention_trend_section_html` 추가**

`src/step5_assemble.py`에서 `build_radar_section_html` 함수 바로 다음에 추가:

```python
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
```

- [ ] **Step 4: `build_index_html`에 파라미터 추가 및 섹션 삽입**

`src/step5_assemble.py`에서 `build_index_html`의 시그니처:

```python
def build_index_html(
    dashboard_dir: Path,
    state_path: Path,
    issues_path: Path | None = None,
    now: str | None = None,
    latest_core_count: int | None = None,
    latest_headlines: list[str] | None = None,
    radar_data: dict | None = None,
    pending_keywords: list[dict] | None = None,
) -> str:
```

을 다음으로 교체한다:

```python
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
```

같은 함수 안에서 다음 블록:

```python
    if radar_data:
        parts.append(build_radar_section_html(radar_data))
```

을 다음으로 교체한다:

```python
    if radar_data:
        parts.append(build_radar_section_html(radar_data))

    if mention_trend_data:
        parts.append(build_mention_trend_section_html(mention_trend_data, cold_start_stage))
```

docstring의 `Args:` 블록에도 두 파라미터 설명을 추가한다:

```
        mention_trend_data: step_mention_trend.run() 결과 (Phase 5, 선택). cold_start_stage가
            "hidden"이면 호출부가 아예 넘기지 않아 섹션이 렌더링되지 않는다.
        cold_start_stage: step_mention_trend.cold_start_stage() 결과. "preview"면 섹션 제목에
            "(참고용)" 라벨이 붙는다.
```

- [ ] **Step 5: CSS 클래스 추가**

`src/step5_assemble.py`의 `_DASHBOARD_CSS`에서 다음 줄:

```
.chip.stock-down{background:rgba(194,59,59,.1);color:#C23B3B;border-color:transparent}
```

다음 줄 바로 뒤에 추가:

```
.chip.warn-chip{background:var(--warn-bg);border:1px solid var(--warn-line);color:#A9790B}
```

- [ ] **Step 6: 테스트 실행해 통과 확인**

Run: `python -m pytest tests/test_step5_assemble.py -v`
Expected: PASS (기존 테스트 전부 + 신규 5개)

- [ ] **Step 7: 커밋**

```bash
git add src/step5_assemble.py tests/test_step5_assemble.py
git commit -m "feat: render mention-trend section on index.html with cold-start preview label"
```

---

### Task 8: `main.py` — 파이프라인에 두 신규 Step 연결

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `step_stock_price.load_watch_tickers`, `step_stock_price.run`,
  `step_stock_price.match_articles_to_stocks` (Task 2·3), `step_mention_trend.load_tech_keywords`,
  `step_mention_trend.run`, `step_mention_trend.count_accumulated_days`,
  `step_mention_trend.cold_start_stage` (Task 4·5), `step5_assemble.run(...,
  mention_trend_data=None, cold_start_stage="active")` (Task 7의 `build_index_html`을
  내부에서 호출하는 기존 `run()` 함수 — 이번 태스크에서 `step5_assemble.run()` 자체에도
  같은 두 파라미터를 추가해 전달한다)
- Produces: 없음 (오케스트레이션 변경만)

이 태스크는 `main.py`(오케스트레이터, 기존에도 단위 테스트가 없다)와 `step5_assemble.run()`의
파라미터 전달 배선을 다룬다. `main.py` 자체는 이 코드베이스에 테스트 파일이 없으므로(다른
헬퍼인 `_compute_collection_stats`도 마찬가지) TDD 대상에서 제외하고, 구문 검증 + 전체
회귀 테스트로 검증한다.

- [ ] **Step 1: `step5_assemble.run()`에 파라미터 추가**

`src/step5_assemble.py`에서 `run()`의 시그니처:

```python
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
    repo_url: str | None = None,
) -> str:
```

을 다음으로 교체한다:

```python
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
    repo_url: str | None = None,
    mention_trend_data: dict | None = None,
    cold_start_stage: str = "active",
) -> str:
```

같은 함수 안, `index_html = build_index_html(` 호출 블록:

```python
    index_html = build_index_html(
        dashboard_dir,
        Path(state_path),
        issues_path=Path(issues_path) if issues_path else None,
        radar_data=radar_data,
    )
```

을 다음으로 교체한다:

```python
    index_html = build_index_html(
        dashboard_dir,
        Path(state_path),
        issues_path=Path(issues_path) if issues_path else None,
        radar_data=radar_data,
        mention_trend_data=mention_trend_data,
        cold_start_stage=cold_start_stage,
    )
```

docstring `Args:`에도 한 줄씩 추가:

```
        mention_trend_data: 언급량 트렌드 데이터 (Phase 5, 선택). build_index_html로 그대로 전달된다.
        cold_start_stage: 콜드 스타트 단계 (Phase 5). build_index_html로 그대로 전달된다.
```

- [ ] **Step 2: `main.py` import 및 초기값 추가**

`main.py`에서 다음 import 블록:

```python
from src import (
    notify,
    radar_weekly,
    run_status,
    step0_init,
    step1_collect,
    step2_dedup,
    step3_classify,
    step4_5_issue_match,
    step4_summarize,
    step5_assemble,
    step6_send,
)
```

을 다음으로 교체한다:

```python
from src import (
    notify,
    radar_weekly,
    run_status,
    step0_init,
    step1_collect,
    step2_dedup,
    step3_classify,
    step4_5_issue_match,
    step4_summarize,
    step5_assemble,
    step6_send,
    step_mention_trend,
    step_stock_price,
)
```

`main()` 함수 안, `steps_completed = []` 다음 줄:

```python
    steps_completed = []
    raw_articles = []
```

을 다음으로 교체한다(예외 발생 시 `except` 블록에서도 항상 정의돼 있어야 하므로 초기값을 미리 둔다):

```python
    steps_completed = []
    raw_articles = []
    trend_data = None
    cold_start_stage = "hidden"
```

- [ ] **Step 3: Step 4.5(이슈 매칭) 다음, 레이더 호출 전에 두 신규 Step 삽입**

`main.py`에서 다음 블록:

```python
        core_articles = [a for a in summarized_articles if not a.get("summary_fallback")]
        step4_5_issue_match.run(core_articles, config["company_aliases"], paths["issues"], today)
        steps_completed.append("issue_match")

        _maybe_run_weekly_radar(base_dir, config, today, datetime.now(KST).weekday())
```

을 다음으로 교체한다:

```python
        core_articles = [a for a in summarized_articles if not a.get("summary_fallback")]
        step4_5_issue_match.run(core_articles, config["company_aliases"], paths["issues"], today)
        steps_completed.append("issue_match")

        trends_dir = base_dir / "data" / "trends"
        tech_keywords = step_mention_trend.load_tech_keywords(base_dir / "config" / "tech_keywords.yaml")
        accumulated_days = step_mention_trend.count_accumulated_days(str(trends_dir), today)
        cold_start_stage = step_mention_trend.cold_start_stage(accumulated_days)

        trend_data = step_mention_trend.run(
            classified_articles, config["company_aliases"], tech_keywords, str(trends_dir), today
        )
        steps_completed.append("mention_trend")

        watch_tickers = step_stock_price.load_watch_tickers(base_dir / "config" / "watch_tickers.yaml")
        stock_data = step_stock_price.run(
            watch_tickers, str(base_dir / "data" / "stock" / f"{today}.json"), today
        )
        steps_completed.append("stock_price")

        if cold_start_stage == "hidden":
            trend_data = None
        else:
            summarized_articles = step_stock_price.match_articles_to_stocks(summarized_articles, stock_data)

        _maybe_run_weekly_radar(base_dir, config, today, datetime.now(KST).weekday())
```

- [ ] **Step 4: `step5_assemble.run()` 호출에 두 값 전달**

`main.py`에서 다음 블록:

```python
        step5_assemble.run(
            summarized_articles,
            pending_review,
            collection_stats,
            paths["archive"],
            paths["dashboard_dir"],
            today,
            paths["state"],
            paths["issues"],
            radar_data=step5_assemble.load_latest_radar(base_dir / "data" / "radar"),
            repo_url=repo_url,
        )
```

을 다음으로 교체한다:

```python
        step5_assemble.run(
            summarized_articles,
            pending_review,
            collection_stats,
            paths["archive"],
            paths["dashboard_dir"],
            today,
            paths["state"],
            paths["issues"],
            radar_data=step5_assemble.load_latest_radar(base_dir / "data" / "radar"),
            repo_url=repo_url,
            mention_trend_data=trend_data,
            cold_start_stage=cold_start_stage,
        )
```

- [ ] **Step 5: 실패 경로의 `build_index_html` 재생성 호출에도 반영**

`main.py`의 `except Exception as exc:` 블록 안, 다음 호출:

```python
        index_html = step5_assemble.build_index_html(
            paths["dashboard_dir"],
            paths["state"],
            issues_path=paths["issues"],
            radar_data=step5_assemble.load_latest_radar(base_dir / "data" / "radar"),
            pending_keywords=step5_assemble.load_pending_keywords(pending_path),
        )
```

을 다음으로 교체한다:

```python
        index_html = step5_assemble.build_index_html(
            paths["dashboard_dir"],
            paths["state"],
            issues_path=paths["issues"],
            radar_data=step5_assemble.load_latest_radar(base_dir / "data" / "radar"),
            pending_keywords=step5_assemble.load_pending_keywords(pending_path),
            mention_trend_data=trend_data,
            cold_start_stage=cold_start_stage,
        )
```

성공 경로 마지막의 동일한 `build_index_html` 호출(`main()` 함수 맨 끝)도 똑같이 두 인자를
추가한다.

- [ ] **Step 6: 구문 검증 + 임포트 확인**

Run: `python -m py_compile main.py src/step5_assemble.py`
Expected: 에러 없음 (exit code 0)

Run: `python -c "import main"`
Expected: 에러 없음 — 모든 신규 임포트(`step_mention_trend`, `step_stock_price`)가 정상
해석되는지 확인한다.

- [ ] **Step 7: 커밋**

```bash
git add main.py src/step5_assemble.py
git commit -m "feat: wire stock price and mention trend steps into the daily pipeline"
```

---

### Task 9: 전체 회귀 테스트 실행

**Files:**
- 변경 없음 (검증 전용 태스크)

- [ ] **Step 1: 전체 테스트 스위트 실행**

Run: `python -m pytest -v`
Expected: 모든 테스트 PASS. 특히 다음이 포함돼야 한다:
- `tests/test_config_data.py` (2 tests)
- `tests/test_step_stock_price.py` (7 tests)
- `tests/test_step_mention_trend.py` (10 tests)
- `tests/test_step5_assemble.py` (기존 테스트 전부 + 신규 8개)
- 기존 스위트 전부(`test_step1_collect.py`, `test_step2_dedup.py`, `test_step4_summarize.py`,
  `test_rebuild_dashboard.py` 등) — 시그니처를 모두 하위 호환(기본값 있는 신규 kwarg만 추가)으로
  바꿨으므로 그대로 통과해야 한다.

- [ ] **Step 2: 실패하는 테스트가 있으면 원인 조사 후 수정**

특히 `tests/test_rebuild_dashboard.py`가 `step5_assemble.build_index_html`/`build_dashboard_html`을
호출한다면, 신규 kwarg 기본값(`mention_trend_data=None`, `cold_start_stage="active"`) 때문에
동작이 달라지지 않는지 확인한다 — `mention_trend_data`를 넘기지 않으면 섹션이 렌더링되지
않아야 하므로 기존 출력과 동일해야 한다.

- [ ] **Step 3: 최종 확인 커밋 (수정이 있었던 경우에만)**

```bash
git add -A
git commit -m "test: fix regressions found in Phase 5 full suite run"
```

수정이 없었다면 이 커밋은 생략한다.
