"""Example MA-crossover strategy for Phase 2 acceptance."""

from __future__ import annotations

from typing import Any, Dict

import polars as pl

from quantmind.domain import DataSource, Interval, PositionSize, TimeUnit, TradingStrategy
from quantmind.indicators import crossunder, ema, crossover


class MovingAverageCrossoverStrategy(TradingStrategy):
    """Long-only EMA crossover strategy."""

    algorithm_id = "moving-average-crossover"
    market = "NSE"
    product_type = "CNC"
    long_only = True
    time_unit = TimeUnit.DAY
    interval = 1

    def __init__(
        self,
        symbol: str = "RELIANCE",
        interval: Interval | str = "day",
        fast_period: int = 20,
        slow_period: int = 50,
    ):
        self.symbol = symbol.upper()
        self.fast_period = fast_period
        self.slow_period = slow_period

        data_sources = [
            DataSource(
                symbol=self.symbol,
                interval=interval,
                warmup_window=slow_period + 10,
            )
        ]

        super().__init__(
            algorithm_id=self.algorithm_id,
            symbols=[self.symbol],
            market=self.market,
            product_type=self.product_type,
            long_only=self.long_only,
            time_unit=self.time_unit,
            interval=self.interval,
            data_sources=data_sources,
            position_sizes=[
                PositionSize(symbol=self.symbol, percentage_of_portfolio=100.0)
            ],
        )
        self.set_parameters(
            {
                "symbol": self.symbol,
                "interval": str(self.data_sources[0].interval.value),
                "fast_period": fast_period,
                "slow_period": slow_period,
            }
        )

    def _prepare(self, df: pl.DataFrame) -> pl.DataFrame:
        df = ema(df, period=self.fast_period, result_column="ema_fast")
        df = ema(df, period=self.slow_period, result_column="ema_slow")
        df = crossover(
            df, first_column="ema_fast", second_column="ema_slow", result_column="x_up"
        )
        df = crossunder(
            df,
            first_column="ema_fast",
            second_column="ema_slow",
            result_column="x_dn",
        )
        return df

    def generate_buy_signals(
        self, data: Dict[str, pl.DataFrame]
    ) -> Dict[str, pl.Series]:
        key = next(iter(data))
        df = self._prepare(data[key])
        sig = df["x_up"].fill_null(False).cast(pl.Boolean)
        return {self.symbol: sig}

    def generate_sell_signals(
        self, data: Dict[str, pl.DataFrame]
    ) -> Dict[str, pl.Series]:
        key = next(iter(data))
        df = self._prepare(data[key])
        sig = df["x_dn"].fill_null(False).cast(pl.Boolean)
        return {self.symbol: sig}

    def prepare_data(self, data: Dict[str, pl.DataFrame]) -> Dict[str, pl.DataFrame]:
        key = next(iter(data))
        return {key: self._prepare(data[key])}
