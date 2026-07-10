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
