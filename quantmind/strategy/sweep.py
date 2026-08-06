"""Parameter sweep helper for strategies."""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Type

from ..domain.strategy import TradingStrategy

logger = logging.getLogger(__name__)


@dataclass
class SweepResult:
    """Result of a parameter sweep."""

    results: List[Dict[str, Any]]
    best: Dict[str, Any] | None = None
    best_metric: float | None = None


def _make_strategy_instance(
    strategy_class: Type[TradingStrategy],
    base_kwargs: Dict[str, Any],
    params: Dict[str, Any],
) -> TradingStrategy:
    kwargs = {**base_kwargs, **params}
    return strategy_class(**kwargs)


class ParameterGrid:
    """Exhaustive grid of parameter combinations."""

    def __init__(self, grid: Dict[str, Iterable[Any]]):
        self.grid = grid

    def __iter__(self):
        keys = list(self.grid.keys())
        values = [self.grid[k] for k in keys]
        for combo in itertools.product(*values):
            yield dict(zip(keys, combo))

    def __len__(self) -> int:
        total = 1
        for v in self.grid.values():
            try:
                total *= len(v)
            except TypeError:
                return 0
        return total


def sweep(
    strategy_class: Type[TradingStrategy],
    parameter_grid: ParameterGrid,
    run_backtest: Callable[[TradingStrategy], Dict[str, Any]],
    base_kwargs: Dict[str, Any] | None = None,
    maximize: str = "total_return",
) -> SweepResult:
    """Run a strategy for each parameter combination and return the best run.

    Args:
        strategy_class: Strategy class to instantiate.
        parameter_grid: Iterable of parameter dicts.
        run_backtest: Callable that accepts a strategy instance and returns a
            result dict containing at least the metric named by `maximize`.
        base_kwargs: Static kwargs passed to every strategy instance.
        maximize: Name of the metric to maximize.

    Returns:
        SweepResult containing all runs and the best run.
    """
    base_kwargs = base_kwargs or {}
    results: List[Dict[str, Any]] = []
    best: Dict[str, Any] | None = None
    best_metric: float | None = None

    logger.info("Starting parameter sweep over %d combinations", len(parameter_grid))

    for params in parameter_grid:
        logger.debug("Running parameters: %s", params)
        try:
            strategy = _make_strategy_instance(strategy_class, base_kwargs, params)
            result = run_backtest(strategy)
            combined = {"parameters": params, **result}
            results.append(combined)

            metric = combined.get(maximize)
            if metric is not None and (best_metric is None or metric > best_metric):
                best_metric = metric
                best = combined
        except Exception as exc:
            logger.warning("Parameter combination %s failed: %s", params, exc)
            results.append({"parameters": params, "error": str(exc)})

    return SweepResult(results=results, best=best, best_metric=best_metric)
