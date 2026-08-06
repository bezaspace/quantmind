import json
from datetime import date

import pytest

from quantmind.data.cache import OHLCVCache
from quantmind.data.providers.upstox import UpstoxDataProvider


@pytest.fixture
def tmp_cache(tmp_path):
    return OHLCVCache(cache_dir=tmp_path)


@pytest.fixture
def instrument_json():
    return [
        {
            "segment": "NSE_EQ",
            "name": "RELIANCE INDUSTRIES LTD",
            "exchange": "NSE",
            "isin": "INE002A01018",
            "instrument_type": "EQ",
            "instrument_key": "NSE_EQ|INE002A01018",
            "lot_size": 1,
            "freeze_quantity": 100000.0,
            "exchange_token": "2885",
            "tick_size": 5.0,
            "trading_symbol": "RELIANCE",
            "short_name": "RELIANCE",
            "security_type": "NORMAL",
            "cas_eligible": True,
        }
    ]


@pytest.fixture
def upstox_provider(tmp_cache, instrument_json, monkeypatch):
    """Upstox provider with a fake token and a small cached instrument master."""
    instruments_dir = tmp_cache.cache_dir / "instruments"
    instruments_dir.mkdir(parents=True, exist_ok=True)
    (instruments_dir / "NSE.json").write_text(json.dumps(instrument_json))

    provider = UpstoxDataProvider(access_token="dummy-token", cache=tmp_cache)
    return provider


@pytest.fixture
def sample_candles():
    return [
        ["2024-08-05T00:00:00+05:30", 100.0, 105.0, 99.0, 104.0, 1000, 0],
        ["2024-08-06T00:00:00+05:30", 104.0, 106.0, 103.0, 105.0, 2000, 0],
    ]
