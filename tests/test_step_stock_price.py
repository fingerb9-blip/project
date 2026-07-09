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


def test_run_omits_ticker_when_fetch_fails_and_no_previous_value_exists(tmp_path, monkeypatch):
    stock_dir = tmp_path / "stock"
    stock_dir.mkdir()
    # NO previous day file created - ticker should be omitted

    def _raise(*a, **k):
        raise RuntimeError("network error")

    monkeypatch.setattr(step_stock_price.stock, "get_market_ohlcv_by_date", _raise)
    watch_tickers = [{"name": "삼성전자", "ticker": "005930"}]
    output_path = stock_dir / "2026-07-09.json"

    result = step_stock_price.run(watch_tickers, str(output_path), "2026-07-09")

    assert result["tickers"] == []


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
