"""Bridge between Pipeline output and TradingStrategy signals."""

from __future__ import annotations

from typing import Any, Dict

import polars as pl

from ..domain import DataSource, TradingStrategy
from ..domain.models import Interval, TimeUnit
from .factor import Factor
from .pipeline import Pipeline
from .pipeline_engine import run_pipeline


class PipelineMomentumStrategy(TradingStrategy):
    """Long-only strategy that holds the top-N pipeline-ranked symbols."""

    time_unit = TimeUnit.DAY
    interval = 1

    def __init__(
        self,
        symbols: list,
        pipeline: type[Pipeline],
        top_n: int = 1,
        rank_column: str = "rank",
    ):
        super().__init__(
            symbols=symbols,
            data_sources=[
                DataSource(symbol=s, interval=Interval.DAY) for s in symbols
            ],
        )
        self.pipeline = pipeline
        self.top_n = int(top_n)
        self.rank_column = rank_column
        self._signals: Dict[str, pl.Series] = {}

    def prepare_data(self, data: Dict[str, pl.DataFrame]) -> Dict[str, pl.DataFrame]:
        from .panel import dict_to_long_form

        panel = dict_to_long_form(data)
        result = run_pipeline(panel, self.pipeline)
        self._pipeline_output = result
        self._signals = self._build_signals(data, result)
        return data

    def _build_signals(
        self,
        data: Dict[str, pl.DataFrame],
        pipeline_output: pl.DataFrame,
    ) -> Dict[str, pl.Series]:
        # For each symbol, create a boolean series aligned to its DataFrame
        signals: Dict[str, pl.Series] = {}
        for key, df in data.items():
            sym = key.split("_")[0].upper()
            # Align pipeline result to this symbol
            sym_result = pipeline_output.filter(pl.col("symbol") == sym)
            merged = df.select(["Datetime"]).join(
                sym_result.select(["datetime", pl.col(self.rank_column).alias("__rank__")]),
                left_on="Datetime",
                right_on="datetime",
                how="left",
            )
            buy = (
                merged["__rank__"]
                .fill_null(9999.0)
                .lt(self.top_n + 1)
                & merged["__rank__"].is_not_null()
            )
            signals[sym] = buy
        return signals

    def generate_buy_signals(self, data: Dict[str, pl.DataFrame]) -> Dict[str, pl.Series]:
        return self._signals

    def generate_sell_signals(self, data: Dict[str, pl.DataFrame]) -> Dict[str, pl.Series]:
        buy = self.generate_buy_signals(data)
        return {sym: ~s for sym, s in buy.items()}
