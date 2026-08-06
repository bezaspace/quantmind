"""Core domain models for QuantMind."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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

    @property
    def amount_of_minutes(self) -> float:
        mapping = {
            Interval.MINUTE_1: 1,
            Interval.MINUTE_3: 3,
            Interval.MINUTE_5: 5,
            Interval.MINUTE_15: 15,
            Interval.MINUTE_30: 30,
            Interval.MINUTE_60: 60,
            Interval.DAY: 60 * 24,
            Interval.WEEK: 60 * 24 * 7,
            Interval.MONTH: 60 * 24 * 30,
        }
        return mapping[self]


class DataType(str, Enum):
    """Supported data types for a data source."""

    OHLCV = "OHLCV"
    TICK = "TICK"
    ORDER_BOOK = "ORDER_BOOK"


class TimeUnit(str, Enum):
    """Time unit for strategy scheduling."""

    MINUTE = "MINUTE"
    HOUR = "HOUR"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"

    @classmethod
    def from_value(cls, value: str) -> "TimeUnit":
        normalized = value.upper().strip()
        if normalized.endswith("S"):
            normalized = normalized[:-1]
        return cls(normalized)

    @property
    def amount_of_minutes(self) -> float:
        mapping = {
            TimeUnit.MINUTE: 1,
            TimeUnit.HOUR: 60,
            TimeUnit.DAY: 60 * 24,
            TimeUnit.WEEK: 60 * 24 * 7,
            TimeUnit.MONTH: 60 * 24 * 30,
        }
        return mapping[self]

    @property
    def single_name(self) -> str:
        return self.value.lower()

    @property
    def plural_name(self) -> str:
        return self.single_name + "s"

    def create_date(self, start: date, interval: int) -> date:
        if self is TimeUnit.MINUTE:
            return start
        if self is TimeUnit.HOUR:
            return start
        if self is TimeUnit.DAY:
            return start + timedelta(days=interval)
        if self is TimeUnit.WEEK:
            return start + timedelta(weeks=interval)
        if self is TimeUnit.MONTH:
            return start + timedelta(days=30 * interval)
        raise ValueError(f"Unsupported time unit: {self}")


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


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
    """Descriptor for a market-data request used by a strategy."""

    symbol: str
    interval: Interval
    identifier: Optional[str] = None
    data_type: DataType = field(default=DataType.OHLCV)
    warmup_window: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    exchange: str = "NSE"
    provider: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.interval, str):
            object.__setattr__(
                self, "interval", Interval.from_value(self.interval)
            )
        if isinstance(self.data_type, str):
            object.__setattr__(
                self, "data_type", DataType(self.data_type.upper())
            )
        if self.identifier is None:
            object.__setattr__(
                self, "identifier", f"{self.symbol.upper()}_{self.interval.value}"
            )
