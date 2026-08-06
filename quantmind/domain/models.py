"""Core domain models for QuantMind."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional


class Interval(str, Enum):
    """Supported OHLCV intervals, mapped to Upstox/Yahoo Finance strings."""

    MINUTE_1 = "1minute"
    MINUTE_3 = "3minute"
    MINUTE_5 = "5minute"
    MINUTE_15 = "15minute"
    MINUTE_30 = "30minute"
    MINUTE_60 = "60minute"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"

    @classmethod
    def from_value(cls, value: str) -> "Interval":
        """Resolve a string to an Interval, accepting common aliases."""
        aliases = {
            "1m": cls.MINUTE_1,
            "1min": cls.MINUTE_1,
            "3m": cls.MINUTE_3,
            "5m": cls.MINUTE_5,
            "15m": cls.MINUTE_15,
            "30m": cls.MINUTE_30,
            "30min": cls.MINUTE_30,
            "60m": cls.MINUTE_60,
            "1h": cls.MINUTE_60,
            "1d": cls.DAY,
            "daily": cls.DAY,
            "1w": cls.WEEK,
            "weekly": cls.WEEK,
            "1wk": cls.WEEK,
            "1mo": cls.MONTH,
            "monthly": cls.MONTH,
        }
        normalized = value.lower().strip()
        if normalized in aliases:
            return aliases[normalized]
        return cls(normalized)

    @property
    def is_intraday(self) -> bool:
        return self.value.endswith("minute")


@dataclass(frozen=True)
class Instrument:
    """A tradable instrument on an Indian exchange."""

    symbol: str
    trading_symbol: str
    name: str
    exchange: str
    segment: str
    isin: str
    instrument_key: str
    instrument_type: str
    lot_size: int
    tick_size: float


@dataclass(frozen=True)
class DataSource:
    """Descriptor for a market-data request."""

    symbol: str
    interval: Interval
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    exchange: str = "NSE"
    provider: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.interval, str):
            object.__setattr__(
                self, "interval", Interval.from_value(self.interval)
            )
