from datetime import date

from quantmind.domain.calendar import TradingCalendar


def test_is_trading_day_weekend():
    cal = TradingCalendar()
    assert not cal.is_trading_day(date(2024, 8, 3))  # Saturday
    assert not cal.is_trading_day(date(2024, 8, 4))  # Sunday
    assert cal.is_trading_day(date(2024, 8, 6))  # Tuesday


def test_holiday_2024_independence_day():
    cal = TradingCalendar()
    assert not cal.is_trading_day(date(2024, 8, 15))


def test_trading_days_between():
    cal = TradingCalendar()
    days = cal.trading_days_between(date(2024, 8, 1), date(2024, 8, 10))
    assert date(2024, 8, 3) not in days
    assert date(2024, 8, 15) not in days
    assert all(d.weekday() < 5 for d in days)
