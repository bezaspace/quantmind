"""Deterministic accuracy tests for the VectorBacktest engine."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from quantmind.backtesting import SimpleBacktest, VectorBacktest
from quantmind.domain import (
    DataSource,
    Interval,
    PositionSize,
    StopLossRule,
    TakeProfitRule,
    TradingCost,
    TradingStrategy,
)
from quantmind.domain.models import TimeUnit


def _df(dates, close):
    return pl.DataFrame(
        {
            "Datetime": dates,
            "Open": close,
            "High": [c + 1 for c in close],
            "Low": [c - 1 for c in close],
            "Close": close,
            "Volume": [1000] * len(close),
        }
    )


class StaticSignalStrategy(TradingStrategy):
    """Strategy that fires deterministic buy/sell signals by bar index."""

    time_unit = TimeUnit.DAY
    interval = 1

    def __init__(
        self,
        symbol: str,
        buy_bars: set,
        sell_bars: set,
        stop_losses=None,
        take_profits=None,
        trading_costs=None,
    ):
        super().__init__(
            symbols=[symbol],
            data_sources=[DataSource(symbol=symbol, interval=Interval.DAY)],
            position_sizes=[PositionSize(symbol=symbol, percentage_of_portfolio=100)],
            stop_losses=stop_losses or [],
            take_profits=take_profits or [],
            trading_costs=trading_costs or [],
        )
        self.symbol = symbol
        self.buy_bars = set(buy_bars)
        self.sell_bars = set(sell_bars)

    def _signals(self, data):
        key = next(iter(data))
        n = len(data[key])
        return {
            self.symbol: pl.Series(
                "signal", [i in self.buy_bars for i in range(n)]
            )
        }

    def generate_buy_signals(self, data):
        key = next(iter(data))
        n = len(data[key])
        return {
            self.symbol: pl.Series("buy", [i in self.buy_bars for i in range(n)])
        }

    def generate_sell_signals(self, data):
        key = next(iter(data))
        n = len(data[key])
        return {
            self.symbol: pl.Series("sell", [i in self.sell_bars for i in range(n)])
        }


def test_buy_and_hold_no_costs():
    """Buy at 100, sell at 110, no costs -> exactly 10% return."""
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(5)]
    close = [100.0, 101.0, 102.0, 104.0, 110.0]
    df = _df(dates, close)
    strategy = StaticSignalStrategy("RELIANCE", buy_bars={0}, sell_bars={4})
    result = VectorBacktest(strategy, {"RELIANCE": df}, initial_capital=10_000).run()
    assert result.total_return == pytest.approx(0.10, abs=1e-9)
    assert result.num_trades == 1


def test_buy_and_sell_with_costs():
    """Hand-calculate return with 0.1% fee and 0.05% slippage per side."""
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(2)]
    close = [100.0, 110.0]
    df = _df(dates, close)
    cost = TradingCost(
        symbol="RELIANCE", fee_percentage=0.1, slippage_percentage=0.05
    )
    strategy = StaticSignalStrategy(
        "RELIANCE",
        buy_bars={0},
        sell_bars={1},
        trading_costs=[cost],
    )
    result = VectorBacktest(strategy, {"RELIANCE": df}, initial_capital=10_000).run()

    # Expected
    buy_fill = 100.0 * (1 + 0.05 / 100)
    buy_fee = 10_000 * 0.1 / 100
    net_capital = 10_000 - buy_fee
    qty = net_capital / buy_fill
    sell_fill = 110.0 * (1 - 0.05 / 100)
    gross = qty * sell_fill
    sell_fee = gross * 0.1 / 100
    final = gross - sell_fee
    expected_return = (final - 10_000) / 10_000

    assert result.total_return == pytest.approx(expected_return, abs=1e-6)
    assert result.num_trades == 1


def test_fixed_stop_loss_exit():
    """Buy at 100, then a 5% stop is hit the next bar."""
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(3)]
    close = [100.0, 90.0, 90.0]
    # low of bar 1 = 89, so the 5% stop at 95 is breached
    high = [101.0, 91.0, 91.0]
    low = [99.0, 89.0, 89.0]
    df = pl.DataFrame(
        {
            "Datetime": dates,
            "Open": close,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": [1000] * 3,
        }
    )
    strategy = StaticSignalStrategy(
        "RELIANCE",
        buy_bars={0},
        sell_bars=set(),
        stop_losses=[StopLossRule(symbol="RELIANCE", percentage_threshold=5)],
    )
    result = VectorBacktest(strategy, {"RELIANCE": df}, initial_capital=10_000).run()
    # The engine exits at min(close, stop_price). close=90, stop=95 -> 90
    # Quantity = 10_000 / 100 = 100; final cash = 100 * 90 = 9_000
    assert result.total_return == pytest.approx(-0.10, abs=1e-9)
    assert result.num_trades == 1
    stop_row = result.trades.filter(pl.col("Reason") == "stop_loss")
    assert stop_row.height == 1
    assert stop_row["Price"][0] == pytest.approx(90.0, abs=1e-9)


def test_fixed_take_profit_exit():
    """Buy at 100, then a 5% take-profit is hit."""
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(2)]
    close = [100.0, 105.0]
    high = [101.0, 105.0]
    low = [99.0, 100.0]
    df = pl.DataFrame(
        {
            "Datetime": dates,
            "Open": close,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": [1000] * 2,
        }
    )
    strategy = StaticSignalStrategy(
        "RELIANCE",
        buy_bars={0},
        sell_bars=set(),
        take_profits=[TakeProfitRule(symbol="RELIANCE", percentage_threshold=5)],
    )
    result = VectorBacktest(strategy, {"RELIANCE": df}, initial_capital=10_000).run()
    assert result.total_return == pytest.approx(0.05, abs=1e-9)
    tp_row = result.trades.filter(pl.col("Reason") == "take_profit")
    assert tp_row.height == 1
    assert tp_row["Price"][0] == pytest.approx(105.0, abs=1e-9)


def test_trailing_stop():
    """Price rises to 120 then drops; 5% trailing stop should lock in 10% gain."""
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(3)]
    close = [100.0, 120.0, 110.0]
    high = [101.0, 120.0, 115.0]
    low = [99.0, 119.0, 90.0]
    df = pl.DataFrame(
        {
            "Datetime": dates,
            "Open": close,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": [1000] * 3,
        }
    )
    strategy = StaticSignalStrategy(
        "RELIANCE",
        buy_bars={0},
        sell_bars=set(),
        stop_losses=[StopLossRule(symbol="RELIANCE", percentage_threshold=5, trailing=True)],
    )
    result = VectorBacktest(strategy, {"RELIANCE": df}, initial_capital=10_000).run()
    # Trailing stop becomes 120 * 0.95 = 114. Bar 2 close 110 < 114 -> exit at 110
    assert result.total_return == pytest.approx(0.10, abs=1e-9)
    stop_row = result.trades.filter(pl.col("Reason") == "stop_loss")
    assert stop_row.height == 1
    assert stop_row["Price"][0] == pytest.approx(110.0, abs=1e-9)


def test_matches_simple_backtest():
    """VectorBacktest and SimpleBacktest should produce the same trade list for a single asset."""
    from examples.moving_average_crossover import MovingAverageCrossoverStrategy

    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(120)]
    close = [100.0 + i * 0.1 for i in range(120)]
    df = _df(dates, close)
    strategy = MovingAverageCrossoverStrategy(symbol="RELIANCE", fast_period=5, slow_period=20)

    vector_result = VectorBacktest(strategy, {"RELIANCE": df}, initial_capital=100_000).run()
    simple_result = SimpleBacktest(strategy, {"RELIANCE": df}, initial_capital=100_000).run()

    assert vector_result.num_trades == simple_result.num_trades
    assert vector_result.total_return == pytest.approx(simple_result.total_return, abs=1e-6)
    assert vector_result.max_drawdown == pytest.approx(simple_result.max_drawdown, abs=1e-6)
