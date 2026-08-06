"""Built-in cross-sectional factors for pipelines."""

from __future__ import annotations

from typing import Any, Dict, List

import polars as pl

from ..factor import Factor


def _col(panel: pl.DataFrame, name: str) -> pl.Expr:
    """Get a column by case-insensitive name."""
    lower = name.lower()
    for c in panel.columns:
        if c.lower() == lower:
            return pl.col(c)
    raise KeyError(f"Column '{name}' not found in panel")


def _get_series(panel: pl.DataFrame, name: str) -> pl.Series:
    lower = name.lower()
    for c in panel.columns:
        if c.lower() == lower:
            return panel[c]
    raise KeyError(f"Column '{name}' not found in panel")


class Returns(Factor):
    """Percentage returns over ``window`` bars."""

    inputs = ["close"]

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        return (
            panel.with_columns(
                _col(panel, "close")
                .pct_change(self.window)
                .over("symbol")
                .alias("__ret__")
            )
        )["__ret__"]


class Latest(Factor):
    """Latest value of an OHLCV column."""

    def __init__(self, column: str = "close") -> None:
        super().__init__(window=1)
        self.column = column.lower()
        self.inputs = [self.column]

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        return _get_series(panel, self.column)


class SMA(Factor):
    """Simple moving average of ``close``."""

    inputs = ["close"]

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        return (
            panel.with_columns(
                _col(panel, "close")
                .rolling_mean(window_size=self.window, min_samples=self.window)
                .over("symbol")
                .alias("__sma__")
            )
        )["__sma__"]


class EMA(Factor):
    """Exponential moving average of ``close``."""

    inputs = ["close"]

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        return (
            panel.with_columns(
                _col(panel, "close")
                .ewm_mean(span=float(self.window))
                .over("symbol")
                .alias("__ema__")
            )
        )["__ema__"]


class AverageDollarVolume(Factor):
    """Average dollar volume over ``window`` bars."""

    inputs = ["close", "volume"]

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        return (
            panel.with_columns(
                (_col(panel, "close") * _col(panel, "volume"))
                .rolling_mean(window_size=self.window, min_samples=self.window)
                .over("symbol")
                .alias("__adv__")
            )
        )["__adv__"]


class StaticPerSymbol(Factor):
    """A static string/value mapping per symbol (e.g. sector labels)."""

    inputs: List[str] = []

    def __init__(self, mapping: Dict[str, Any]) -> None:
        super().__init__(window=1)
        self.mapping = {k.upper(): v for k, v in mapping.items()}

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        symbols = panel["symbol"].to_list()
        return pl.Series(
            "__static__",
            [self.mapping.get(str(s).upper()) for s in symbols],
        )

    def required_columns(self) -> List[str]:
        return []
