"""NSE/BSE trading calendar."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

import nse_calendar


class TradingCalendar:
    """Calendar of NSE trading holidays. BSE holidays are modelled with the
    same set in v1 because they largely overlap."""

    def __init__(self, weekends: bool = True):
        self.weekends = weekends

    def is_trading_day(self, dt: date) -> bool:
        """Return True if the given date is a trading day."""
        if self.weekends and dt.weekday() >= 5:
            return False
        return dt not in self._holidays_for_year(dt.year)

    def next_trading_day(self, dt: date) -> date:
        """Return the next trading day on or after dt."""
        while not self.is_trading_day(dt):
            dt += timedelta(days=1)
        return dt

    def previous_trading_day(self, dt: date) -> date:
        """Return the previous trading day on or before dt."""
        while not self.is_trading_day(dt):
            dt -= timedelta(days=1)
        return dt

    def trading_days_between(
        self, start: date, end: date, inclusive: bool = True
    ) -> list[date]:
        """Return all trading days between start and end."""
        days: list[date] = []
        cursor = start
        stop = end if inclusive else end - timedelta(days=1)
        while cursor <= stop:
            if self.is_trading_day(cursor):
                days.append(cursor)
            cursor += timedelta(days=1)
        return days

    def is_holiday(self, dt: date) -> bool:
        return dt in self._holidays_for_year(dt.year)

    def get_holidays(self, start: date, end: date) -> list[date]:
        """Return holidays within a date range."""
        result = []
        for year in range(start.year, end.year + 1):
            for h in self._holidays_for_year(year):
                if start <= h <= end:
                    result.append(h)
        return sorted(set(result))

    def _holidays_for_year(self, year: int) -> set[date]:
        """Load NSE holidays for a given year and cache by year."""
        if not hasattr(self, "_cache"):
            self._cache: dict[int, set[date]] = {}
        if year not in self._cache:
            raw = nse_calendar.get_holidays(year)
            holidays = set()
            for item in raw:
                d = item.get("date")
                if isinstance(d, str):
                    holidays.add(datetime.strptime(d, "%Y-%m-%d").date())
                elif isinstance(d, date):
                    holidays.add(d)
            self._cache[year] = holidays
        return self._cache[year]
