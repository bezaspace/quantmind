from datetime import datetime, timedelta

import polars as pl

from quantmind.domain import DataSource, Interval, PositionSize, TimeUnit, TradingStrategy
from quantmind.backtesting import SimpleBacktest
from quantmind.strategy import ParameterGrid, sweep


def _synthetic_df(n=120):
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(n)]
    close = [100.0 + 10 * (i / n) for i in range(n)]
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


class _TestStrategy(TradingStrategy):
    time_unit = TimeUnit.DAY
    interval = 1

    def __init__(self, threshold: int = 1):
        super().__init__(
            symbols=["RELIANCE"],
            data_sources=[DataSource(symbol="RELIANCE", interval=Interval.DAY)],
            position_sizes=[PositionSize(symbol="RELIANCE", fixed_amount=10000)],
        )
        self.threshold = threshold
        self.set_parameters({"threshold": threshold})

    def generate_buy_signals(self, data):
        df = next(iter(data.values()))
        return {self.symbols[0]: pl.Series("buy", [True] * len(df))}

    def generate_sell_signals(self, data):
        return {self.symbols[0]: pl.Series("sell", [False] * len(data[next(iter(data))]))}


def test_parameter_grid_iteration():
    grid = ParameterGrid({"a": [1, 2], "b": [10, 20]})
    combos = list(grid)
    assert len(combos) == 4
    assert {"a": 1, "b": 10} in combos


def test_parameter_sweep():
    df = _synthetic_df(60)
    data = {"RELIANCE": df}

    def run_backtest(strategy):
        bt = SimpleBacktest(strategy, data, initial_capital=100_000)
        result = bt.run()
        return {"total_return": result.total_return}

    grid = ParameterGrid({"threshold": [1, 2, 3]})
    result = sweep(_TestStrategy, grid, run_backtest)

    assert len(result.results) == 3
    assert result.best is not None
    assert "parameters" in result.best
    assert "total_return" in result.best
