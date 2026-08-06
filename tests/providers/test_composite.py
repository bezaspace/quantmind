from datetime import date, datetime
from typing import Optional

from unittest.mock import patch

import pandas as pd
import polars as pl

from quantmind.data.providers import (
    ChainedDataProvider,
    DataProvider,
    YahooFinanceDataProvider,
)
from quantmind.domain.exceptions import DataProviderError
from quantmind.domain.models import Interval


class FailingProvider(DataProvider):
    name = "FAILING"
    supported_intervals = {Interval.DAY}

    def get_ohlcv(
        self,
        symbol,
        interval,
        start=None,
        end=None,
        exchange="NSE",
    ):
        raise DataProviderError("always fails")

    def resolve_instrument(self, symbol, exchange="NSE"):
        return {"symbol": symbol}


def test_chained_resolve_fallback(tmp_cache):
    failing = FailingProvider(cache=tmp_cache)
    yahoo = YahooFinanceDataProvider(cache=tmp_cache)
    chain = ChainedDataProvider([failing, yahoo])

    result = chain.resolve_instrument("RELIANCE")
    assert result is not None


def test_chained_get_ohlcv_fallback(tmp_cache):
    dates = pd.date_range("2024-08-01", "2024-08-05", freq="D")
    mock_df = pd.DataFrame(
        {
            "Open": [100.0] * 5,
            "High": [105.0] * 5,
            "Low": [99.0] * 5,
            "Close": [104.0] * 5,
            "Volume": [1000] * 5,
        },
        index=dates,
    )

    with patch("yfinance.Ticker.history", return_value=mock_df):
        failing = FailingProvider(cache=tmp_cache)
        yahoo = YahooFinanceDataProvider(cache=tmp_cache)
        chain = ChainedDataProvider([failing, yahoo])

        df = chain.get_ohlcv(
            "RELIANCE", "day", start="2024-08-01", end="2024-08-05"
        )
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 5
