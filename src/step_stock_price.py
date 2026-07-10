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
    조회된 마지막 행(가장 최근 거래일)을 사용한다. 브리핑이 09:00 개장 후 돌면 이 값은
    당일 장중 시세(실행 시점 가격)이며, 저장 후 다음 실행 전까지 그대로 고정 표시된다.

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
