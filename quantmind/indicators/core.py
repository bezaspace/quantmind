"""Pure-Polars technical indicator helpers.

These are intentionally dependency-free (no TA-Lib) and operate on the
standard QuantMind OHLCV schema: Datetime, Open, High, Low, Close, Volume.
"""

from __future__ import annotations

from typing import Optional

import polars as pl


def _get_column(col: str | pl.Expr) -> pl.Expr:
    return pl.col(col) if isinstance(col, str) else col


def sma(
    df: pl.DataFrame,
    period: int,
    column: str = "Close",
    result_column: Optional[str] = None,
) -> pl.DataFrame:
    """Simple moving average."""
    result_column = result_column or f"sma_{period}"
    return df.with_columns(
        _get_column(column).rolling_mean(window_size=period).alias(result_column)
    )


def ema(
    df: pl.DataFrame,
    period: int,
    column: str = "Close",
    result_column: Optional[str] = None,
) -> pl.DataFrame:
    """Exponential moving average (standard smoothing)."""
    result_column = result_column or f"ema_{period}"
    return df.with_columns(
        _get_column(column).ewm_mean(span=period, adjust=False).alias(result_column)
    )


def rsi(
    df: pl.DataFrame,
    period: int = 14,
    column: str = "Close",
    result_column: Optional[str] = None,
) -> pl.DataFrame:
    """Relative Strength Index using Wilder's smoothing."""
    result_column = result_column or f"rsi_{period}"
    close = _get_column(column)
    delta = close.diff()
    gain = pl.when(delta > 0).then(delta).otherwise(0)
    loss = pl.when(delta < 0).then(-delta).otherwise(0)

    # Wilder's smoothing corresponds to alpha = 1/period, i.e. com = period - 1
    avg_gain = gain.ewm_mean(com=period - 1, adjust=False)
    avg_loss = loss.ewm_mean(com=period - 1, adjust=False)
    rs = avg_gain / avg_loss
    rsi_value = pl.when(avg_loss == 0).then(100).otherwise(100 - (100 / (1 + rs)))

    return df.with_columns(rsi_value.alias(result_column))


def macd(
    df: pl.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    column: str = "Close",
    result_prefix: Optional[str] = None,
) -> pl.DataFrame:
    """MACD line, signal line, and histogram."""
    prefix = result_prefix or "macd"
    close = _get_column(column)
    fast_ema = close.ewm_mean(span=fast, adjust=False)
    slow_ema = close.ewm_mean(span=slow, adjust=False)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm_mean(span=signal, adjust=False)
    histogram = macd_line - signal_line

    return df.with_columns(
        [
            macd_line.alias(f"{prefix}_line"),
            signal_line.alias(f"{prefix}_signal"),
            histogram.alias(f"{prefix}_histogram"),
        ]
    )


def bollinger_bands(
    df: pl.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
    column: str = "Close",
    upper_band_column: Optional[str] = None,
    middle_band_column: Optional[str] = None,
    lower_band_column: Optional[str] = None,
) -> pl.DataFrame:
    """Bollinger Bands with a simple moving average."""
    upper_band_column = upper_band_column or "bb_upper"
    middle_band_column = middle_band_column or "bb_middle"
    lower_band_column = lower_band_column or "bb_lower"

    close = _get_column(column)
    middle = close.rolling_mean(window_size=period)
    std = close.rolling_std(window_size=period)
    upper = middle + std * std_dev
    lower = middle - std * std_dev

    return df.with_columns(
        [
            upper.alias(upper_band_column),
            middle.alias(middle_band_column),
            lower.alias(lower_band_column),
        ]
    )


def atr(
    df: pl.DataFrame,
    period: int = 14,
    high_column: str = "High",
    low_column: str = "Low",
    close_column: str = "Close",
    result_column: Optional[str] = None,
) -> pl.DataFrame:
    """Average True Range using Wilder's smoothing."""
    result_column = result_column or f"atr_{period}"
    high = _get_column(high_column)
    low = _get_column(low_column)
    close = _get_column(close_column)

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pl.max_horizontal([tr1, tr2, tr3])
    atr_value = true_range.ewm_mean(com=period - 1, adjust=False)

    return df.with_columns(atr_value.alias(result_column))


def returns(
    df: pl.DataFrame,
    period: int = 1,
    column: str = "Close",
    result_column: Optional[str] = None,
) -> pl.DataFrame:
    """Period-over-period returns."""
    result_column = result_column or f"returns_{period}"
    close = _get_column(column)
    return df.with_columns(
        (close / close.shift(period) - 1).alias(result_column)
    )


def volatility(
    df: pl.DataFrame,
    period: int = 20,
    column: str = "Close",
    result_column: Optional[str] = None,
) -> pl.DataFrame:
    """Rolling standard deviation of returns."""
    result_column = result_column or f"volatility_{period}"
    close = _get_column(column)
    ret = close / close.shift(1) - 1
    return df.with_columns(ret.rolling_std(window_size=period).alias(result_column))


def crossover(
    df: pl.DataFrame,
    first_column: str,
    second_column: str,
    result_column: str = "crossover",
) -> pl.DataFrame:
    """True when first crosses above second."""
    first = _get_column(first_column)
    second = _get_column(second_column)
    signal = (first > second) & (first.shift(1) <= second.shift(1))
    return df.with_columns(signal.fill_null(False).alias(result_column))


def crossunder(
    df: pl.DataFrame,
    first_column: str,
    second_column: str,
    result_column: str = "crossunder",
) -> pl.DataFrame:
    """True when first crosses below second."""
    first = _get_column(first_column)
    second = _get_column(second_column)
    signal = (first < second) & (first.shift(1) >= second.shift(1))
    return df.with_columns(signal.fill_null(False).alias(result_column))


def add_basic_liquidity(
    df: pl.DataFrame,
    volume_period: int = 20,
    result_column: Optional[str] = None,
) -> pl.DataFrame:
    """Average dollar volume proxy: Close * Volume rolling mean."""
    result_column = result_column or "adtv"
    return df.with_columns(
        ((pl.col("Close") * pl.col("Volume")).rolling_mean(window_size=volume_period))
        .alias(result_column)
    )
