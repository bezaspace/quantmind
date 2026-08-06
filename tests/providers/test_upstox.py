import polars as pl
import pytest


def test_resolve_instrument(upstox_provider):
    instrument = upstox_provider.resolve_instrument("RELIANCE", "NSE")
    assert instrument["instrument_key"] == "NSE_EQ|INE002A01018"


def test_resolve_unknown_symbol_raises(upstox_provider):
    with pytest.raises(Exception):
        upstox_provider.resolve_instrument("UNKNOWN", "NSE")


def test_get_ohlcv_daily(upstox_provider, sample_candles):
    class MockResponse:
        status_code = 200

        def json(self):
            return {"status": "success", "data": {"candles": sample_candles}}

    upstox_provider._http.get = lambda url: MockResponse()

    df = upstox_provider.get_ohlcv(
        "RELIANCE", "day", start="2024-08-05", end="2024-08-06"
    )

    assert isinstance(df, pl.DataFrame)
    assert list(df.columns) == ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    assert len(df) == 2
    assert df["Close"].to_list() == [104.0, 105.0]


def test_get_ohlcv_chunked_one_minute(upstox_provider):
    """Verify that a request spanning more than 30 days is split into chunks."""
    calls = []

    class MockResponse:
        status_code = 200

        def json(self):
            return {"status": "success", "data": {"candles": []}}

    def fake_get(url):
        calls.append(url)
        return MockResponse()

    upstox_provider._http.get = fake_get

    upstox_provider.get_ohlcv(
        "RELIANCE", "1minute", start="2024-06-01", end="2024-08-06"
    )

    assert len(calls) >= 2


def test_get_ohlcv_rate_limit_raises(upstox_provider):
    class MockResponse:
        status_code = 429
        text = "rate limited"

    upstox_provider._http.get = lambda url: MockResponse()

    with pytest.raises(Exception):
        upstox_provider.get_ohlcv(
            "RELIANCE", "day", start="2024-08-05", end="2024-08-06"
        )
