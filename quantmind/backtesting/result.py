"""Backtest result and helper utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

import polars as pl


@dataclass
class BacktestResult:
    """Result of a single backtest run."""

    equity_curve: pl.DataFrame
    trades: pl.DataFrame
    total_return: float
    max_drawdown: float
    num_trades: int
    win_rate: float
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestRun(BacktestResult):
    """A named/identifiable backtest run."""

    backtest_id: Optional[str] = None
    name: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class Backtest:
    """Backtest configuration container.

    A ``Backtest`` stores the setup for one or more runs and can be executed
    through a runner such as ``VectorBacktest``.
    """

    strategy: "TradingStrategy"
    data: Dict[str, pl.DataFrame]
    initial_capital: float = 100_000.0
    start_date: Optional[Any] = None
    end_date: Optional[Any] = None
    backtest_id: Optional[str] = None
    name: Optional[str] = None
    dynamic_position_sizing: bool = True


def max_drawdown(equity_series: pl.Series) -> float:
    """Compute maximum drawdown from an equity series."""
    values = equity_series.to_list()
    if not values:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd
