from datetime import datetime, timedelta

import polars as pl
import pytest

from quantmind.pipeline import Pipeline, run_pipeline
from quantmind.pipeline.factor import Factor
from quantmind.pipeline.factors.builtin import (
    AverageDollarVolume,
    Latest,
    Returns,
    SMA,
    StaticPerSymbol,
)
from quantmind.pipeline.filter import Filter


def _panel(n_bars: int = 10, n_symbols: int = 3, seed: int = 0):
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(n_bars)]
    rows = []
    for i, d in enumerate(dates):
        for j in range(n_symbols):
            close = 100.0 + (i + 1) * (j + 1) + seed
            volume = 1000.0 * (j + 1)
            rows.append(
                {
                    "Datetime": d,
                    "Symbol": f"SYM{j}",
                    "Open": close - 1,
                    "High": close + 1,
                    "Low": close - 2,
                    "Close": close,
                    "Volume": volume,
                }
            )
    return pl.DataFrame(rows)


def test_returns_factor():
    panel = _panel(n_bars=10, n_symbols=2)
    result = run_pipeline(panel, type("P", (Pipeline,), {"ret": Returns(window=2)}))
    assert "ret" in result.columns
    assert result.height > 0
    # first two bars for each symbol are null (pct_change 2)
    assert result.filter(pl.col("ret").is_null()).height == 4


def test_sma_factor():
    panel = _panel(n_bars=10, n_symbols=2)
    result = run_pipeline(panel, type("P", (Pipeline,), {"sma": SMA(window=3)}))
    assert "sma" in result.columns
    # first two rows per symbol null (min_periods=3)
    assert result.filter(pl.col("sma").is_null()).height == 4


def test_top_filter():
    panel = _panel(n_bars=10, n_symbols=5)

    class P(Pipeline):
        close = Latest("close")
        universe = AverageDollarVolume(window=2).top(3)
        rank = close.rank(mask=universe)

    result = run_pipeline(panel, P)
    assert "rank" in result.columns
    # Should contain only top-3 adv symbols per bar
    per_bar = result.group_by("datetime").agg(pl.len()).sort("datetime")
    assert all(c <= 3 for c in per_bar["len"].to_list())


def test_zscore_and_demean():
    panel = _panel(n_bars=10, n_symbols=5)

    class P(Pipeline):
        ret = Returns(window=2)
        z = ret.zscore()
        demeaned = ret.demean()

    result = run_pipeline(panel, P)
    assert "z" in result.columns
    assert "demeaned" in result.columns
    # z-score per bar should have mean ~0 and std ~1 for non-null rows
    numeric = result.filter(pl.col("z").is_not_null())
    means = numeric.group_by("datetime").agg(pl.col("z").mean()).sort("datetime")
    for m in means["z"].to_list():
        assert abs(m) < 1e-6


def test_factor_arithmetic():
    panel = _panel(n_bars=10, n_symbols=2)

    class P(Pipeline):
        ret = Returns(window=2)
        double_ret = ret * 2

    result = run_pipeline(panel, P)
    assert "double_ret" in result.columns
    assert (
        result.filter(pl.col("ret").is_not_null())
        .with_columns((pl.col("ret") * 2).alias("expected"))
        .filter(pl.col("double_ret") != pl.col("expected"))
        .is_empty()
    )


def test_static_per_symbol_groups():
    panel = _panel(n_bars=10, n_symbols=4)
    mapping = {"SYM0": "A", "SYM1": "A", "SYM2": "B", "SYM3": "B"}

    class P(Pipeline):
        ret = Returns(window=2)
        z = ret.zscore(groups=mapping)

    result = run_pipeline(panel, P)
    assert "z" in result.columns


def test_pipeline_requires_columns():
    class P(Pipeline):
        ret = Returns(window=2)
        sma = SMA(window=3)

    cols = P.required_columns()
    assert "close" in cols


def test_pipeline_error_no_columns():
    with pytest.raises(TypeError):

        class Empty(Pipeline):
            pass
