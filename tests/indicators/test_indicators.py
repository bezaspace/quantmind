from datetime import datetime, timedelta

import polars as pl
import pytest

from quantmind.indicators import (
    bollinger_bands,
    crossover,
    crossunder,
    ema,
    macd,
    rsi,
    sma,
)


def _make_df(values):
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(len(values))]
    return pl.DataFrame(
        {
            "Datetime": dates,
            "Open": values,
            "High": [v + 1 for v in values],
            "Low": [v - 1 for v in values],
            "Close": values,
            "Volume": [1000] * len(values),
        }
    )


def test_sma_basic():
    df = _make_df([1.0, 2.0, 3.0, 4.0, 5.0])
    df = sma(df, period=3)
    assert df["sma_3"].to_list()[2] == 2.0
    assert df["sma_3"].to_list()[4] == 4.0


def test_ema_basic():
    df = _make_df([1.0, 2.0, 3.0, 4.0, 5.0])
    df = ema(df, period=3)
    # With span=3, alpha = 2/(3+1) = 0.5 and adjust=False
    # EMA_3 = 0.5*3 + 0.5*EMA_2 = 0.5*3 + 0.5*1.5 = 2.25
    values = df["ema_3"].to_list()
    assert values[2] == pytest.approx(2.25, abs=1e-9)


def test_rsi_returns_reasonable_range():
    # Strong uptrend
    df = _make_df([i * 1.0 for i in range(1, 31)])
    df = rsi(df, period=14)
    rsi_values = df["rsi_14"].to_list()
    assert all(v is None or (0 <= v <= 100) for v in rsi_values)
    # Last value should be near 100 after a long uptrend
    assert rsi_values[-1] > 70


def test_macd_columns_added():
    df = _make_df([i * 1.0 for i in range(1, 61)])
    df = macd(df, fast=12, slow=26, signal=9)
    assert "macd_line" in df.columns
    assert "macd_signal" in df.columns
    assert "macd_histogram" in df.columns


def test_bollinger_bands_basic():
    df = _make_df([1.0, 2.0, 3.0, 4.0, 5.0] * 5)
    df = bollinger_bands(df, period=5, std_dev=2.0)
    for col in ["bb_upper", "bb_middle", "bb_lower"]:
        assert col in df.columns
    assert all(u >= m >= l for u, m, l in zip(
        df["bb_upper"].to_list()[4:],
        df["bb_middle"].to_list()[4:],
        df["bb_lower"].to_list()[4:],
    ))


def test_crossover_and_crossunder():
    a = [1.0, 2.0, 3.0, 2.0, 1.0]
    b = [2.0, 2.0, 2.0, 3.0, 3.0]
    df = _make_df([0.0] * 5)
    df = df.with_columns([
        pl.Series("a", a),
        pl.Series("b", b),
    ])
    df = crossover(df, "a", "b", result_column="x_up")
    df = crossunder(df, "a", "b", result_column="x_dn")
    assert df["x_up"].to_list() == [False, False, True, False, False]
    assert df["x_dn"].to_list() == [False, False, False, True, False]
