"""주가 데이터 수집 — Yahoo Finance 비공식 차트 API (무료, API 키 불필요).

대시보드 "오늘의 시장 현황" 패널의 주가 추이 카드에 쓰인다. step5_assemble.py는
이 모듈이 저장한 JSON만 읽어 렌더링하며 네트워크 호출은 하지 않는다(§ 대시보드
생성 코드는 기사 데이터·통계만 사용).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

_CHART_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_HEADERS = {"User-Agent": "Mozilla/5.0"}
_TIMEOUT = 10
_DEFAULT_TICKERS = {"삼성전자": "005930.KS", "SK하이닉스": "000660.KS"}


def fetch_price_history(ticker: str, range_: str = "1mo") -> list[dict]:
    """Yahoo Finance 차트 API로 일별 종가 히스토리를 가져온다.

    Args:
        ticker: Yahoo Finance 티커 (예: "005930.KS")
        range_: 조회 기간 (예: "1mo")

    Returns:
        [{"date": "YYYY-MM-DD", "close": float}, ...] 날짜순 리스트. 휴장일 등으로
        종가가 없는(null) 항목은 제외한다.

    Raises:
        RuntimeError: 요청 실패 또는 응답 형식이 예상과 다른 경우
    """
    try:
        response = requests.get(
            _CHART_ENDPOINT.format(ticker=ticker),
            headers=_HEADERS,
            params={"range": range_, "interval": "1d"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (requests.exceptions.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError(f"{ticker} 주가 조회 실패: {exc}") from exc

    history = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        history.append({"date": day, "close": round(close, 2)})
    return history


def run(output_path: str, tickers: dict[str, str] | None = None) -> dict[str, list[dict]]:
    """여러 종목의 가격 히스토리를 가져와 저장한다.

    특정 종목 조회가 실패해도 파이프라인을 막지 않고 해당 종목만 건너뛴다. 이전에
    저장된 데이터가 있으면 실패한 종목의 값은 그대로 유지해(조용한 열화 방지) 차트가
    하루 사이에 사라지지 않게 한다.

    Args:
        output_path: data/state/stock_prices.json 저장 경로
        tickers: {표시명: 티커} dict (기본값: 삼성전자/SK하이닉스)

    Returns:
        {표시명: [{"date", "close"}, ...]} dict (저장된 최종 데이터)
    """
    tickers = tickers or _DEFAULT_TICKERS
    output_path = Path(output_path)

    existing = {}
    if output_path.exists():
        with output_path.open(encoding="utf-8") as f:
            existing = json.load(f)

    result = dict(existing)
    for name, ticker in tickers.items():
        try:
            result[name] = fetch_price_history(ticker)
        except RuntimeError as exc:
            logger.error("주가 조회 실패, 이전 데이터 유지: %s", exc)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result
