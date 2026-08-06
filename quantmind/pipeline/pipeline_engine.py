"""Engine that runs a Pipeline on a long-form OHLCV panel."""

from __future__ import annotations

import logging
from contextvars import copy_context
from typing import Any, Dict, Optional

import polars as pl

from .factor import _EVAL_CACHE, Factor
from .filter import Filter
from .pipeline import Pipeline

logger = logging.getLogger(__name__)


def _normalize_panel(panel: pl.DataFrame) -> pl.DataFrame:
    """Lower-case OHLCV column names; keep ``datetime`` and ``symbol``."""
    rename_map: Dict[str, str] = {}
    for c in panel.columns:
        low = c.lower()
        if low in ("datetime", "symbol"):
            rename_map[c] = low
        elif low in ("open", "high", "low", "close", "volume"):
            rename_map[c] = low
        else:
            rename_map[c] = c
    panel = panel.rename(rename_map)
    # Ensure datetime is Datetime
    if panel["datetime"].dtype != pl.Datetime:
        panel = panel.with_columns(pl.col("datetime").cast(pl.Datetime("us")))
    return panel


class PipelineEngine:
    """Run a :class:`Pipeline` against a long-form panel."""

    def run(
        self,
        panel: pl.DataFrame,
        pipeline: type[Pipeline],
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
    ) -> pl.DataFrame:
        panel = _normalize_panel(panel)
        if start_date is not None:
            start = self._to_dt(start_date)
            panel = panel.filter(pl.col("datetime") >= start)
        if end_date is not None:
            end = self._to_dt(end_date)
            panel = panel.filter(pl.col("datetime") <= end)

        columns = pipeline.get_columns()
        universe = pipeline.get_universe()

        cache: Dict[tuple, pl.Series] = {}
        token = _EVAL_CACHE.set(cache)
        try:
            result = panel.select(["datetime", "symbol"])
            for name, factor in columns.items():
                values = factor.evaluate(panel)
                result = result.with_columns(values.alias(name))

            if universe is not None:
                mask = universe.evaluate(panel)
                result = result.with_columns(mask.alias("__in_universe__"))
                result = result.filter(pl.col("__in_universe__"))
                result = result.drop("__in_universe__")
        finally:
            _EVAL_CACHE.reset(token)

        return result

    def run_pipeline(
        self,
        panel: pl.DataFrame,
        pipeline: type[Pipeline],
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
    ) -> pl.DataFrame:
        return self.run(panel, pipeline, start_date, end_date)

    def _to_dt(self, value: Any) -> Any:
        return value


def run_pipeline(
    panel: pl.DataFrame,
    pipeline: type[Pipeline],
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
) -> pl.DataFrame:
    return PipelineEngine().run(panel, pipeline, start_date, end_date)
