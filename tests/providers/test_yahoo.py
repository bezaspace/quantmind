from unittest.mock import patch

import pandas as pd
import polars as pl

from quantmind.data.providers import YahooFinanceDataProvider


def test_yahoo_get_ohlcv(tmp_cache):
    dates = pd.date_range("2024-08-01", "2024-08-05", freq="D")
    mock_df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "High": [105.0, 106.0, 107.0, 108.0, 109.0],
            "Low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "Close": [104.0, 105.0, 106.0, 107.0, 108.0],
            "Volume": [1000, 2000, 3000, 4000, 5000],
        },
        index=dates,
    )

    with patch("yfinance.Ticker.history", return_value=mock_df):
        provider = YahooFinanceDataProvider(cache=tmp_cache)
        df = provider.get_ohlcv(
            "RELIANCE", "day", start="2024-08-01", end="2024-08-05"
        )

    assert isinstance(df, pl.DataFrame)
    assert len(df) == 5
    assert "Datetime" in df.columns
    assert df["Close"].to_list() == [104.0, 105.0, 106.0, 107.0, 108.0]
