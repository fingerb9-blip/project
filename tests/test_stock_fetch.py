import json
from unittest.mock import Mock, patch

import pytest
import requests

from src import stock_fetch


def _yahoo_response(timestamps, closes):
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {"quote": [{"close": closes}]},
                }
            ]
        }
    }


def test_fetch_price_history_parses_response():
    payload = _yahoo_response([1751328000, 1751414400], [72000.0, 73500.0])
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = payload
    mock_response.raise_for_status = Mock()

    with patch("src.stock_fetch.requests.get", return_value=mock_response):
        history = stock_fetch.fetch_price_history("005930.KS")

    assert history == [
        {"date": "2025-07-01", "close": 72000.0},
        {"date": "2025-07-02", "close": 73500.0},
    ]


def test_fetch_price_history_skips_null_closes():
    payload = _yahoo_response([1751328000, 1751414400], [72000.0, None])
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = payload
    mock_response.raise_for_status = Mock()

    with patch("src.stock_fetch.requests.get", return_value=mock_response):
        history = stock_fetch.fetch_price_history("005930.KS")

    assert len(history) == 1
    assert history[0]["close"] == 72000.0


def test_fetch_price_history_raises_on_request_error():
    with patch("src.stock_fetch.requests.get", side_effect=requests.exceptions.ConnectionError("boom")):
        with pytest.raises(RuntimeError):
            stock_fetch.fetch_price_history("005930.KS")


def test_fetch_price_history_raises_on_malformed_response():
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = {"chart": {"result": None}}
    mock_response.raise_for_status = Mock()

    with patch("src.stock_fetch.requests.get", return_value=mock_response):
        with pytest.raises(RuntimeError):
            stock_fetch.fetch_price_history("005930.KS")


def test_run_saves_json_for_multiple_tickers(tmp_path):
    output_path = tmp_path / "stock_prices.json"
    history_by_ticker = {
        "005930.KS": [{"date": "2026-07-09", "close": 72000.0}],
        "000660.KS": [{"date": "2026-07-09", "close": 210000.0}],
    }

    with patch("src.stock_fetch.fetch_price_history", side_effect=lambda ticker, **kw: history_by_ticker[ticker]):
        result = stock_fetch.run(
            str(output_path), tickers={"삼성전자": "005930.KS", "SK하이닉스": "000660.KS"}
        )

    assert result["삼성전자"] == history_by_ticker["005930.KS"]
    assert result["SK하이닉스"] == history_by_ticker["000660.KS"]
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == result


def test_run_keeps_previous_data_for_failed_ticker(tmp_path):
    output_path = tmp_path / "stock_prices.json"
    output_path.write_text(
        json.dumps({"삼성전자": [{"date": "2026-07-08", "close": 71000.0}]}),
        encoding="utf-8",
    )

    def fetch(ticker, **kwargs):
        raise RuntimeError("네트워크 오류")

    with patch("src.stock_fetch.fetch_price_history", side_effect=fetch):
        result = stock_fetch.run(str(output_path), tickers={"삼성전자": "005930.KS"})

    assert result["삼성전자"] == [{"date": "2026-07-08", "close": 71000.0}]
