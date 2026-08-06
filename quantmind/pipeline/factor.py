"""Factor base class and cross-sectional operations for pipelines."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

import polars as pl

logger = logging.getLogger(__name__)

# Evaluation cache used by PipelineEngine to avoid recomputing shared factors
_EVAL_CACHE: ContextVar[Optional[Dict[tuple, pl.Series]]] = ContextVar(
    "_pipeline_factor_eval_cache", default=None
)


class Factor:
    """Base class for a cross-sectional factor expression."""

    inputs: List[str] = ["close"]
    window: int = 1

    def __init__(self, window: Optional[int] = None) -> None:
        if window is not None:
            self.window = window
        if self.window is None or self.window < 1:
            raise ValueError(
                f"{type(self).__name__}.window must be a positive integer, "
                f"got {self.window!r}"
            )

    def required_columns(self) -> List[str]:
        return list(self.inputs)

    def required_window(self) -> int:
        return int(self.window)

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        """Compute factor values on a long-form OHLCV panel."""
        raise NotImplementedError

    def evaluate(self, panel: pl.DataFrame) -> pl.Series:
        cache = _EVAL_CACHE.get()
        if cache is None:
            return self.compute_panel(panel)
        key = (id(panel), id(self))
        cached = cache.get(key)
        if cached is not None:
            return cached
        values = self.compute_panel(panel)
        cache[key] = values
        return values

    # Cross-sectional ops
    def rank(self, mask: Optional["Filter"] = None) -> "Factor":
        return _Rank(self, mask=mask)

    def top(self, n: int) -> "Filter":
        from .filter import _TopN
        return _TopN(self, n)

    def bottom(self, n: int) -> "Filter":
        from .filter import _BottomN
        return _BottomN(self, n)

    def zscore(self, mask: Optional["Filter"] = None, groups=None) -> "Factor":
        return _Zscore(self, mask=mask, groups=groups)

    def demean(self, mask: Optional["Filter"] = None, groups=None) -> "Factor":
        return _Demean(self, mask=mask, groups=groups)

    def winsorize(
        self,
        lower: float = 0.01,
        upper: float = 0.99,
        mask: Optional["Filter"] = None,
    ) -> "Factor":
        if not (0.0 <= lower < upper <= 1.0):
            raise ValueError(
                f"winsorize requires 0 <= lower < upper <= 1, "
                f"got lower={lower}, upper={upper}"
            )
        return _Winsorize(self, lower=lower, upper=upper, mask=mask)

    # Arithmetic composition
    def __neg__(self) -> "Factor":
        return _UnaryOp(self, op="neg")

    def __add__(self, other: Any) -> "Factor":
        return _BinaryOp(self, other, op="add")

    def __radd__(self, other: Any) -> "Factor":
        return _BinaryOp(other, self, op="add")

    def __sub__(self, other: Any) -> "Factor":
        return _BinaryOp(self, other, op="sub")

    def __rsub__(self, other: Any) -> "Factor":
        return _BinaryOp(other, self, op="sub")

    def __mul__(self, other: Any) -> "Factor":
        return _BinaryOp(self, other, op="mul")

    def __rmul__(self, other: Any) -> "Factor":
        return _BinaryOp(other, self, op="mul")

    def __truediv__(self, other: Any) -> "Factor":
        return _BinaryOp(self, other, op="div")

    def __rtruediv__(self, other: Any) -> "Factor":
        return _BinaryOp(other, self, op="div")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(window={self.window})"


class _Rank(Factor):
    def __init__(
        self,
        base: Factor,
        mask: Optional["Filter"] = None,
    ) -> None:
        super().__init__(window=base.required_window())
        self._base = base
        self._mask = mask
        self.inputs = list(base.required_columns())
        if mask is not None:
            for col in mask.required_columns():
                if col not in self.inputs:
                    self.inputs.append(col)
            self.window = max(self.window, mask.required_window())

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        values = self._base.evaluate(panel)
        df = panel.select(["datetime", "symbol"]).with_columns(
            values.alias("__rank_input__")
        )
        if self._mask is not None:
            mask_values = self._mask.evaluate(panel)
            df = df.with_columns(
                pl.when(mask_values)
                .then(pl.col("__rank_input__"))
                .otherwise(None)
                .alias("__rank_input__")
            )
        ranked = df.with_columns(
            pl.col("__rank_input__")
            .rank(method="ordinal", descending=False)
            .over("datetime")
            .cast(pl.Float64)
            .alias("__rank__")
        )
        ranked = ranked.with_columns(
            pl.when(pl.col("__rank_input__").is_null())
            .then(None)
            .otherwise(pl.col("__rank__"))
            .alias("__rank__")
        )
        return ranked["__rank__"]


def _coerce_operand(operand: Any) -> Factor:
    if isinstance(operand, Factor):
        return operand
    if isinstance(operand, (int, float)):
        return _Constant(float(operand))
    raise TypeError(
        f"Unsupported operand type for Factor arithmetic: {type(operand).__name__}"
    )


def _coerce_groups(groups: Any) -> Optional[Factor]:
    if groups is None:
        return None
    if isinstance(groups, Factor):
        return groups
    if isinstance(groups, dict):
        from .factors.builtin import StaticPerSymbol
        return StaticPerSymbol(groups)
    raise TypeError(
        f"Unsupported type for `groups`: {type(groups).__name__}. "
        f"Expected None, dict[str, Any], or Factor."
    )


class _Constant(Factor):
    inputs: List[str] = []

    def __init__(self, value: float) -> None:
        super().__init__(window=1)
        self._value = float(value)

    def required_columns(self) -> List[str]:
        return []

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        return pl.Series(
            "__const__", [self._value] * panel.height, dtype=pl.Float64
        )


class _UnaryOp(Factor):
    def __init__(self, base: Factor, op: str) -> None:
        super().__init__(window=base.required_window())
        self._base = base
        self._op = op
        self.inputs = list(base.required_columns())

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        values = self._base.evaluate(panel)
        if self._op == "neg":
            return (-values).rename("__unary__")
        raise ValueError(f"Unknown unary op: {self._op}")


class _BinaryOp(Factor):
    def __init__(self, left: Any, right: Any, op: str) -> None:
        left_f = _coerce_operand(left)
        right_f = _coerce_operand(right)
        super().__init__(
            window=max(left_f.required_window(), right_f.required_window())
        )
        self._left = left_f
        self._right = right_f
        self._op = op
        cols: List[str] = list(left_f.required_columns())
        for c in right_f.required_columns():
            if c not in cols:
                cols.append(c)
        self.inputs = cols

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        left = self._left.evaluate(panel)
        right = self._right.evaluate(panel)
        if self._op == "add":
            out = left + right
        elif self._op == "sub":
            out = left - right
        elif self._op == "mul":
            out = left * right
        elif self._op == "div":
            out = left / right
        else:
            raise ValueError(f"Unknown binary op: {self._op}")
        return out.rename("__binop__")


class _CrossSectionalTransform(Factor):
    def __init__(
        self,
        base: Factor,
        mask: Optional["Filter"] = None,
        groups: Any = None,
    ) -> None:
        super().__init__(window=base.required_window())
        self._base = base
        self._mask = mask
        self._groups = _coerce_groups(groups)
        cols = list(base.required_columns())
        if mask is not None:
            for c in mask.required_columns():
                if c not in cols:
                    cols.append(c)
            self.window = max(self.window, mask.required_window())
        if self._groups is not None:
            for c in self._groups.required_columns():
                if c not in cols:
                    cols.append(c)
            self.window = max(self.window, self._groups.required_window())
        self.inputs = cols

    def _transform_expr(self) -> pl.Expr:
        raise NotImplementedError

    def _group_keys(self) -> List[str]:
        if self._groups is None:
            return ["datetime"]
        return ["datetime", "__group__"]

    def compute_panel(self, panel: pl.DataFrame) -> pl.Series:
        values = self._base.evaluate(panel)
        df = panel.select(["datetime", "symbol"]).with_columns(
            values.alias("__x__")
        )
        if self._mask is not None:
            mask_values = self._mask.evaluate(panel)
            df = df.with_columns(
                pl.when(mask_values)
                .then(pl.col("__x__"))
                .otherwise(None)
                .alias("__x__")
            )
        if self._groups is not None:
            group_values = self._groups.evaluate(panel)
            df = df.with_columns(group_values.alias("__group__"))
        df = df.with_columns(self._transform_expr().alias("__out__"))
        return df["__out__"]


class _Zscore(_CrossSectionalTransform):
    def _transform_expr(self) -> pl.Expr:
        x = pl.col("__x__")
        keys = self._group_keys()
        mean = x.mean().over(keys)
        std = x.std().over(keys)
        return (
            pl.when((std == 0) | std.is_null())
            .then(None)
            .otherwise((x - mean) / std)
        )


class _Demean(_CrossSectionalTransform):
    def _transform_expr(self) -> pl.Expr:
        x = pl.col("__x__")
        keys = self._group_keys()
        return x - x.mean().over(keys)


class _Winsorize(_CrossSectionalTransform):
    def __init__(
        self,
        base: Factor,
        lower: float,
        upper: float,
        mask: Optional["Filter"] = None,
    ) -> None:
        super().__init__(base=base, mask=mask)
        self._lower = float(lower)
        self._upper = float(upper)

    def _transform_expr(self) -> pl.Expr:
        x = pl.col("__x__")
        lo = x.quantile(self._lower).over("datetime")
        hi = x.quantile(self._upper).over("datetime")
        return (
            pl.when(x < lo)
            .then(lo)
            .when(x > hi)
            .then(hi)
            .otherwise(x)
        )
