from datetime import datetime, timedelta

import polars as pl

from quantmind.backtesting import SimpleBacktest
from quantmind.domain import (
    CooldownRule,
    DataSource,
    PositionSize,
    StopLossRule,
    TakeProfitRule,
    TradingCost,
    TradingStrategy,
)
from quantmind.domain.models import Interval, TimeUnit


def _synthetic_df(n=120, seed_base=100.0):
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(n)]
    close = [seed_base + 10 * (i / n) for i in range(n)]
    return pl.DataFrame(
        {
            "Datetime": dates,
            "Open": close,
            "High": [c + 1 for c in close],
            "Low": [c - 1 for c in close],
            "Close": close,
            "Volume": [1000] * n,
        }
    )


class _AlwaysBuy(TradingStrategy):
    time_unit = TimeUnit.DAY
    interval = 1

    def __init__(self):
        super().__init__(
            symbols=["RELIANCE"],
            data_sources=[DataSource(symbol="RELIANCE", interval=Interval.DAY)],
            position_sizes=[PositionSize(symbol="RELIANCE", fixed_amount=10000)],
        )

    def generate_buy_signals(self, data):
        df = next(iter(data.values()))
        return {self.symbols[0]: pl.Series("buy", [True] * len(df))}

    def generate_sell_signals(self, data):
        return {self.symbols[0]: pl.Series("sell", [False] * len(data[next(iter(data))]))}


def test_simple_backtest_long_trend():
    df = _synthetic_df(120)
    strategy = _AlwaysBuy()
    bt = SimpleBacktest(strategy, {"RELIANCE": df}, initial_capital=100_000)
    result = bt.run()
    assert result.num_trades >= 1
    assert result.total_return > 0
    assert result.equity_curve.height == len(df)


def test_simple_backtest_stop_loss():
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(20)]
    # Uptrend then sharp drop
    close = [100.0 + i for i in range(10)] + [80.0] * 10
    df = pl.DataFrame(
        {
            "Datetime": dates,
            "Open": close,
            "High": [c + 1 for c in close],
            "Low": [c - 2 for c in close],
            "Close": close,
            "Volume": [1000] * 20,
        }
    )
    strategy = _AlwaysBuy()
    strategy.stop_losses = [StopLossRule(symbol="RELIANCE", percentage_threshold=5)]
    bt = SimpleBacktest(strategy, {"RELIANCE": df}, initial_capital=100_000)
    result = bt.run()
    # Should exit on stop loss after the drop
    sell = result.trades.filter(pl.col("Reason") == "stop_loss")
    assert sell.height >= 1


def test_simple_backtest_cooldown():
    df = _synthetic_df(60)
    strategy = _AlwaysBuy()
    strategy.cooldowns = [CooldownRule(symbol="RELIANCE", bars=5)]
    bt = SimpleBacktest(strategy, {"RELIANCE": df}, initial_capital=100_000)
    result = bt.run()
    # With cooldown, only one trade should happen (buy then final close)
    assert result.num_trades == 1


def test_simple_backtest_with_costs():
    df = _synthetic_df(120)
    strategy = _AlwaysBuy()
    strategy.trading_costs = [
        TradingCost(symbol="RELIANCE", fee_percentage=0.1, slippage_percentage=0.05)
    ]
    bt = SimpleBacktest(strategy, {"RELIANCE": df}, initial_capital=100_000)
    result = bt.run()
    assert (result.trades["Fee"] > 0).any()
