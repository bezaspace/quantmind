"""Helpers for converting between per-symbol DataFrames and long-form panels."""

from __future__ import annotations

from typing import Dict

import polars as pl


def dict_to_long_form(data: Dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Convert a {symbol: OHLCV DataFrame} mapping into a long-form panel."""
    rows = []
    for key, df in data.items():
        symbol = key.split("_")[0].upper()
        df = df.rename({c: c.lower() for c in df.columns})
        df = df.with_columns(pl.lit(symbol).alias("symbol"))
        # Ensure datetime column is named 'datetime' and is Datetime
        if "datetime" not in df.columns:
            for c in df.columns:
                if df[c].dtype == pl.Datetime:
                    df = df.rename({c: "datetime"})
                    break
        rows.append(df)
    panel = pl.concat(rows, how="diagonal")
    # Make sure datetime is Datetime
    if panel["datetime"].dtype != pl.Datetime:
        panel = panel.with_columns(pl.col("datetime").cast(pl.Datetime("us")))
    return panel
