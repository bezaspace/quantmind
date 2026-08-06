"""Filter base class and cross-sectional selectors for pipelines."""

from __future__ import annotations

from typing import List

import polars as pl

from .factor import Factor


class Filter(Factor):
    """Base class for a boolean cross-sectional filter (is-a Factor)."""

    inputs: List[str] = []

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        """Return a boolean Series aligned with ``panel``."""
        raise NotImplementedError

    def __and__(self, other: "Filter") -> "Filter":
        return _And(self, other)

    def __or__(self, other: "Filter") -> "Filter":
        return _Or(self, other)

    def __invert__(self) -> "Filter":
        return _Not(self)


class _TopN(Filter):
    def __init__(self, factor: Factor, n: int) -> None:
        super().__init__(window=factor.required_window())
        self._factor = factor
        self._n = int(n)
        self.inputs = list(factor.required_columns())

    def required_columns(self) -> List[str]:
        return list(self.inputs)

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        values = self._factor.evaluate(panel)
        df = panel.select(["datetime", "symbol"]).with_columns(
            values.alias("__v__")
        )
        ranked = df.with_columns(
            pl.col("__v__")
            .rank(method="ordinal", descending=True)
            .over("datetime")
            .alias("__rank__")
        )
        return (ranked["__rank__"] <= self._n) & ranked["__v__"].is_not_null()


class _BottomN(Filter):
    def __init__(self, factor: Factor, n: int) -> None:
        super().__init__(window=factor.required_window())
        self._factor = factor
        self._n = int(n)
        self.inputs = list(factor.required_columns())

    def required_columns(self) -> List[str]:
        return list(self.inputs)

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        values = self._factor.evaluate(panel)
        df = panel.select(["datetime", "symbol"]).with_columns(
            values.alias("__v__")
        )
        ranked = df.with_columns(
            pl.col("__v__")
            .rank(method="ordinal", descending=False)
            .over("datetime")
            .alias("__rank__")
        )
        return (ranked["__rank__"] <= self._n) & ranked["__v__"].is_not_null()


class _And(Filter):
    def __init__(self, left: Filter, right: Filter) -> None:
        super().__init__(
            window=max(left.required_window(), right.required_window())
        )
        self._left = left
        self._right = right
        cols = list(left.required_columns())
        for c in right.required_columns():
            if c not in cols:
                cols.append(c)
        self.inputs = cols

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        return self._left.evaluate(panel) & self._right.evaluate(panel)


class _Or(Filter):
    def __init__(self, left: Filter, right: Filter) -> None:
        super().__init__(
            window=max(left.required_window(), right.required_window())
        )
        self._left = left
        self._right = right
        cols = list(left.required_columns())
        for c in right.required_columns():
            if c not in cols:
                cols.append(c)
        self.inputs = cols

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        return self._left.evaluate(panel) | self._right.evaluate(panel)


class _Not(Filter):
    def __init__(self, base: Filter) -> None:
        super().__init__(window=base.required_window())
        self._base = base
        self.inputs = list(base.required_columns())

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        return ~self._base.evaluate(panel)
