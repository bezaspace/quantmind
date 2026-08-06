"""Yahoo Finance fallback data provider."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import polars as pl
import yfinance as yf

from quantmind.data.cache import OHLCVCache
from quantmind.domain.exceptions import DataProviderError
from quantmind.domain.models import Interval

from .base import DataProvider


class YahooFinanceDataProvider(DataProvider):
    """OHLCV provider backed by Yahoo Finance using the ``yfinance`` library.

    Useful for daily/weekly/monthly Indian equities because Yahoo exposes
    multi-year history in a single request.
    """

    name = "YAHOO"
    supported_intervals = {
        Interval.MINUTE_1,
        Interval.MINUTE_3,
        Interval.MINUTE_5,
        Interval.MINUTE_15,
        Interval.MINUTE_30,
        Interval.MINUTE_60,
        Interval.DAY,
        Interval.WEEK,
        Interval.MONTH,
    }

    _INTERVAL_MAP = {
        Interval.MINUTE_1: "1m",
        Interval.MINUTE_3: "3m",
        Interval.MINUTE_5: "5m",
        Interval.MINUTE_15: "15m",
        Interval.MINUTE_30: "30m",
        Interval.MINUTE_60: "60m",
        Interval.DAY: "1d",
        Interval.WEEK: "1wk",
        Interval.MONTH: "1mo",
    }

    def __init__(self, cache: Optional[OHLCVCache] = None):
        super().__init__(cache=cache)

    def get_ohlcv(
        self,
        symbol: str,
        interval: str | Interval,
        start: Optional[date | datetime] = None,
        end: Optional[date | datetime] = None,
        exchange: str = "NSE",
    ) -> pl.DataFrame:
        interval = self._validate_interval(interval)
        start, end = self._normalise_dates(start, end)

        yahoo_symbol = self._to_yahoo_symbol(symbol, exchange)
        yahoo_interval = self._INTERVAL_MAP[interval]
        # yfinance end date is exclusive for daily+
        fetch_end = end + timedelta(days=1)

        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(
            start=start.isoformat(),
            end=fetch_end.isoformat(),
            interval=yahoo_interval,
            auto_adjust=True,
            actions=False,
        )

        if df is None or df.empty:
            raise DataProviderError(
                f"Yahoo Finance returned no data for {yahoo_symbol}"
            )

        df = df.reset_index()
        # yfinance returns the date column as the index; its name may be
        # "Date" or "Datetime" depending on the version.
        date_col = df.columns[0]
        df = df[[date_col, "Open", "High", "Low", "Close", "Volume"]]
        df = df.rename(columns={date_col: "Datetime"})
        df["Datetime"] = df["Datetime"].dt.tz_localize(None)
        df["Volume"] = df["Volume"].fillna(0).astype("int64")

        frame = pl.from_pandas(df)
        return frame.with_columns(
            [
                pl.col("Open").cast(pl.Float64),
                pl.col("High").cast(pl.Float64),
                pl.col("Low").cast(pl.Float64),
                pl.col("Close").cast(pl.Float64),
                pl.col("Volume").cast(pl.Int64),
            ]
        )

    def resolve_instrument(self, symbol: str, exchange: str = "NSE") -> dict:
        """Return a lightweight metadata dict for Yahoo."""
        return {
            "symbol": symbol.upper(),
            "yahoo_symbol": self._to_yahoo_symbol(symbol, exchange),
            "exchange": exchange.upper(),
        }

    @staticmethod
    def _to_yahoo_symbol(symbol: str, exchange: str) -> str:
        symbol = symbol.upper()
        exchange = exchange.upper()
        if ".NS" in symbol or ".BO" in symbol:
            return symbol
        if exchange == "BSE":
            return f"{symbol}.BO"
        return f"{symbol}.NS"
