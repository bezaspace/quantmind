from datetime import datetime, timedelta

import polars as pl

from quantmind.backtesting import VectorBacktest
from quantmind.domain import DataSource, Interval, PositionSize, StopLossRule, TakeProfitRule, TradingCost
from quantmind.domain.models import TimeUnit
from quantmind.domain.strategy import TradingStrategy


def _synthetic_df(n=120, start=100.0, trend=0.0):
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(n)]
    close = [start + i * trend for i in range(n)]
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


def test_vector_backtest_long_trend():
    df = _synthetic_df(120, start=100.0, trend=0.1)
    strategy = _AlwaysBuy()
    bt = VectorBacktest(strategy, {"RELIANCE": df}, initial_capital=100_000)
    result = bt.run()
    assert result.num_trades >= 1
    assert result.total_return > 0
    assert result.equity_curve.height == len(df)


def test_vector_backtest_stop_loss():
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(20)]
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
    bt = VectorBacktest(strategy, {"RELIANCE": df}, initial_capital=100_000)
    result = bt.run()
    assert (result.trades["Reason"] == "stop_loss").any()


def test_vector_backtest_take_profit():
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(20)]
    close = [100.0 + i * 2 for i in range(20)]
    df = pl.DataFrame(
        {
            "Datetime": dates,
            "Open": close,
            "High": [c + 1 for c in close],
            "Low": [c - 1 for c in close],
            "Close": close,
            "Volume": [1000] * 20,
        }
    )
    strategy = _AlwaysBuy()
    strategy.take_profits = [TakeProfitRule(symbol="RELIANCE", percentage_threshold=5)]
    bt = VectorBacktest(strategy, {"RELIANCE": df}, initial_capital=100_000)
    result = bt.run()
    assert (result.trades["Reason"] == "take_profit").any()


def test_vector_backtest_multi_asset():
    df1 = _synthetic_df(60, start=100.0, trend=0.2)
    df2 = _synthetic_df(60, start=200.0, trend=-0.1)

    class _MultiBuy(TradingStrategy):
        time_unit = TimeUnit.DAY
        interval = 1

        def __init__(self):
            super().__init__(
                symbols=["RELIANCE", "TCS"],
                data_sources=[
                    DataSource(symbol="RELIANCE", interval=Interval.DAY),
                    DataSource(symbol="TCS", interval=Interval.DAY),
                ],
                position_sizes=[
                    PositionSize(symbol="RELIANCE", percentage_of_portfolio=50),
                    PositionSize(symbol="TCS", percentage_of_portfolio=50),
                ],
            )

        def generate_buy_signals(self, data):
            return {s: pl.Series("buy", [True] * len(next(iter(data.values())))) for s in self.symbols}

        def generate_sell_signals(self, data):
            return {s: pl.Series("sell", [False] * len(next(iter(data.values())))) for s in self.symbols}

    strategy = _MultiBuy()
    bt = VectorBacktest(strategy, {"RELIANCE": df1, "TCS": df2}, initial_capital=100_000)
    result = bt.run()
    symbols = result.trades["Symbol"].unique().to_list()
    assert "RELIANCE" in symbols and "TCS" in symbols


def test_vector_backtest_with_costs():
    df = _synthetic_df(120, start=100.0, trend=0.1)
    strategy = _AlwaysBuy()
    strategy.trading_costs = [TradingCost(symbol="RELIANCE", fee_percentage=0.1, slippage_percentage=0.05)]
    bt = VectorBacktest(strategy, {"RELIANCE": df}, initial_capital=100_000)
    result = bt.run()
    assert (result.trades["Fee"] > 0).any()
