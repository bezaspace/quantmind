"""Data provider abstractions."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Optional

import polars as pl

from quantmind.data.cache import OHLCVCache
from quantmind.domain.exceptions import DataProviderError, UnsupportedInterval
from quantmind.domain.models import DataSource, Interval

logger = logging.getLogger(__name__)


class DataProvider(ABC):
    """Abstract base class for Indian-market OHLCV data providers."""

    name: str = ""
    supported_intervals: set[Interval] = set()

    def __init__(
        self,
        cache: Optional[OHLCVCache] = None,
    ):
        self.cache = cache or OHLCVCache()

    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        interval: str | Interval,
        start: Optional[date | datetime] = None,
        end: Optional[date | datetime] = None,
        exchange: str = "NSE",
    ) -> pl.DataFrame:
        """Fetch OHLCV data for a symbol."""
        raise NotImplementedError

    @abstractmethod
    def resolve_instrument(
        self, symbol: str, exchange: str = "NSE"
    ) -> dict:
        """Resolve a symbol to provider-native instrument metadata."""
        raise NotImplementedError

    def _validate_interval(self, interval: Interval) -> Interval:
        interval = Interval.from_value(interval) if isinstance(interval, str) else interval
        if interval not in self.supported_intervals:
            raise UnsupportedInterval(
                f"{self.name} does not support {interval.value}"
            )
        return interval

    def _normalise_dates(
        self,
        start: Optional[date | datetime | str],
        end: Optional[date | datetime | str],
    ) -> tuple[date, date]:
        if end is None:
            end = date.today()
        elif isinstance(end, str):
            end = date.fromisoformat(end)
        if isinstance(end, datetime):
            end = end.date()

        if start is None:
            start = end.replace(year=end.year - 5)
        elif isinstance(start, str):
            start = date.fromisoformat(start)
        if isinstance(start, datetime):
            start = start.date()

        if start > end:
            raise DataProviderError("start_date cannot be after end_date")
        return start, end
