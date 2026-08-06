"""Quantitative backtest metrics, implemented in Polars where possible."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import polars as pl

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252


def _daily_returns(equity: pl.DataFrame) -> pl.Series:
    """Daily percentage returns from the equity curve."""
    return equity["TotalEquity"].pct_change().drop_nulls()


def _downside_returns(returns: pl.Series, target: float = 0.0) -> pl.Series:
    """Returns that fall below the target (default 0)."""
    return returns.filter(returns < target)


def total_return_metric(equity: pl.DataFrame) -> float:
    values = equity["TotalEquity"].to_list()
    if not values or values[0] == 0:
        return 0.0
    return (values[-1] - values[0]) / values[0]


def cagr(equity: pl.DataFrame) -> float:
    """Compound Annual Growth Rate from the equity curve."""
    dates = equity["Datetime"].to_list()
    values = equity["TotalEquity"].to_list()
    if len(dates) < 2 or values[0] <= 0:
        return 0.0
    start = dates[0]
    end = dates[-1]
    if not isinstance(start, datetime):
        start = datetime.fromisoformat(str(start))
        end = datetime.fromisoformat(str(end))
    num_days = max((end - start).days, 1)
    years = num_days / 365.0
    growth = values[-1] / values[0]
    if growth <= 0:
        return -1.0
    return growth ** (1 / years) - 1


def annualized_return(equity: pl.DataFrame) -> float:
    """Total return annualized by the number of trading days."""
    n = equity.height
    if n < 2:
        return 0.0
    years = n / TRADING_DAYS_PER_YEAR
    tr = total_return_metric(equity)
    if (1 + tr) <= 0:
        return -1.0
    return (1 + tr) ** (1 / max(years, 1 / TRADING_DAYS_PER_YEAR)) - 1


def annualized_volatility(returns: pl.Series) -> float:
    if returns.len() < 2:
        return 0.0
    return float(returns.std()) * math.sqrt(TRADING_DAYS_PER_YEAR)


def downside_deviation(returns: pl.Series) -> float:
    down = _downside_returns(returns, 0.0)
    if down.len() < 2:
        return 0.0
    return float(down.std(ddof=1)) * math.sqrt(TRADING_DAYS_PER_YEAR)


def sharpe_ratio(returns: pl.Series, risk_free_rate: float = 0.04) -> float:
    """Annualized Sharpe ratio using the supplied risk-free rate."""
    if returns.len() < 2:
        return 0.0
    daily_std = float(returns.std())
    if daily_std < 1e-12:
        return 0.0
    mean_daily = float(returns.mean())
    excess_daily = mean_daily - (risk_free_rate / TRADING_DAYS_PER_YEAR)
    return excess_daily * math.sqrt(TRADING_DAYS_PER_YEAR) / daily_std


def sortino_ratio(returns: pl.Series, risk_free_rate: float = 0.04) -> float:
    if returns.len() < 2:
        return 0.0
    down_dev = downside_deviation(returns)
    if down_dev < 1e-12:
        return 0.0
    mean_daily = float(returns.mean())
    excess_daily = mean_daily - (risk_free_rate / TRADING_DAYS_PER_YEAR)
    return excess_daily * math.sqrt(TRADING_DAYS_PER_YEAR) / down_dev


def max_drawdown_metric(equity: pl.DataFrame) -> float:
    """Maximum peak-to-trough drawdown as a positive fraction."""
    values = equity["TotalEquity"].to_list()
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


def max_drawdown_duration(equity: pl.DataFrame) -> int:
    """Longest drawdown duration in calendar days."""
    dates = equity["Datetime"].to_list()
    values = equity["TotalEquity"].to_list()
    if len(values) < 2:
        return 0
    peak = values[0]
    peak_date = dates[0]
    max_days = 0
    for d, v in zip(dates, values):
        if v >= peak:
            peak = v
            peak_date = d
        if not isinstance(d, datetime):
            d = datetime.fromisoformat(str(d))
        if not isinstance(peak_date, datetime):
            peak_date = datetime.fromisoformat(str(peak_date))
        days = (d - peak_date).days
        if days > max_days:
            max_days = days
    return max_days


def avg_drawdown(equity: pl.DataFrame) -> float:
    """Average drawdown across the equity curve."""
    values = equity["TotalEquity"].to_list()
    if not values:
        return 0.0
    peak = values[0]
    dds = []
    for v in values:
        if v > peak:
            peak = v
        elif peak:
            dds.append((peak - v) / peak)
    return float(sum(dds) / len(dds)) if dds else 0.0


def ulcer_index(equity: pl.DataFrame) -> float:
    values = equity["TotalEquity"].to_list()
    if not values:
        return 0.0
    peak = values[0]
    squares = []
    for v in values:
        if v > peak:
            peak = v
        if peak:
            squares.append(((peak - v) / peak) ** 2)
    return math.sqrt(sum(squares) / len(squares)) if squares else 0.0


def calmar_ratio(equity: pl.DataFrame, risk_free_rate: float = 0.04) -> float:
    c = cagr(equity)
    dd = max_drawdown_metric(equity)
    if dd == 0:
        return 0.0
    return (c - risk_free_rate) / dd


def recovery_factor(equity: pl.DataFrame) -> float:
    tr = total_return_metric(equity)
    dd = max_drawdown_metric(equity)
    if dd == 0:
        return 0.0
    return tr / dd


def _sell_trades(trades: pl.DataFrame) -> pl.DataFrame:
    return trades.filter(pl.col("Side") == "SELL")


def win_rate_metric(trades: pl.DataFrame) -> float:
    sells = _sell_trades(trades)
    n = sells.height
    if n == 0:
        return 0.0
    return float((sells["PnL"] > 0).sum() / n)


def num_trades_metric(trades: pl.DataFrame) -> int:
    return _sell_trades(trades).height


def num_winning_trades(trades: pl.DataFrame) -> int:
    return int((_sell_trades(trades).filter(pl.col("PnL") > 0)).height)


def num_losing_trades(trades: pl.DataFrame) -> int:
    return int((_sell_trades(trades).filter(pl.col("PnL") <= 0)).height)


def gross_profit(trades: pl.DataFrame) -> float:
    return float(_sell_trades(trades).filter(pl.col("PnL") > 0)["PnL"].sum() or 0.0)


def gross_loss(trades: pl.DataFrame) -> float:
    return float(_sell_trades(trades).filter(pl.col("PnL") <= 0)["PnL"].sum() or 0.0)


def net_profit(trades: pl.DataFrame) -> float:
    return float(_sell_trades(trades)["PnL"].sum() or 0.0)


def total_fees(trades: pl.DataFrame) -> float:
    if "Fee" not in trades.columns:
        return 0.0
    return float(trades["Fee"].sum() or 0.0)


def profit_factor(trades: pl.DataFrame) -> float:
    gp = gross_profit(trades)
    gl = abs(gross_loss(trades))
    if gl == 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def avg_trade_return(trades: pl.DataFrame) -> float:
    sells = _sell_trades(trades)
    if sells.height == 0:
        return 0.0
    return float(sells["PnL"].mean())


def avg_winning_trade(trades: pl.DataFrame) -> float:
    wins = _sell_trades(trades).filter(pl.col("PnL") > 0)
    if wins.height == 0:
        return 0.0
    return float(wins["PnL"].mean())


def avg_losing_trade(trades: pl.DataFrame) -> float:
    losses = _sell_trades(trades).filter(pl.col("PnL") <= 0)
    if losses.height == 0:
        return 0.0
    return float(losses["PnL"].mean())


def payoff_ratio(trades: pl.DataFrame) -> float:
    avg_win = avg_winning_trade(trades)
    avg_loss = abs(avg_losing_trade(trades))
    if avg_loss == 0:
        return float("inf") if avg_win > 0 else 0.0
    return avg_win / avg_loss


def trade_expectancy(trades: pl.DataFrame, initial_capital: float = 1.0) -> float:
    """Expectancy = win_rate * avg_win - loss_rate * |avg_loss|."""
    sells = _sell_trades(trades)
    n = sells.height
    if n == 0:
        return 0.0
    wins = sells.filter(pl.col("PnL") > 0)
    losses = sells.filter(pl.col("PnL") <= 0)
    win_rate = wins.height / n
    loss_rate = losses.height / n
    avg_win = float(wins["PnL"].mean() or 0.0)
    avg_loss = abs(float(losses["PnL"].mean() or 0.0))
    return (win_rate * avg_win) - (loss_rate * avg_loss)


def average_trade_duration(trades: pl.DataFrame) -> float:
    """Average duration of round-trip trades in calendar days.

    We pair each SELL with the preceding BUY in chronological order.
    """
    if trades.is_empty():
        return 0.0
    buys = trades.filter(pl.col("Side") == "BUY").sort("Datetime")
    sells = trades.filter(pl.col("Side") == "SELL").sort("Datetime")
    durations = []
    buy_dates = buys["Datetime"].to_list()
    sell_dates = sells["Datetime"].to_list()
    for sell_dt, _ in zip(sell_dates, sells.to_dicts()):
        # find most recent buy before this sell
        preceding = [d for d in buy_dates if d <= sell_dt]
        if preceding:
            d = sell_dt - preceding[-1]
            durations.append(d.days if isinstance(d, timedelta) else d)
    if not durations:
        return 0.0
    return sum(durations) / len(durations)


def max_trade_duration(trades: pl.DataFrame) -> float:
    if trades.is_empty():
        return 0.0
    buys = trades.filter(pl.col("Side") == "BUY").sort("Datetime")
    sells = trades.filter(pl.col("Side") == "SELL").sort("Datetime")
    buy_dates = buys["Datetime"].to_list()
    sell_dates = sells["Datetime"].to_list()
    max_days = 0
    for sell_dt in sell_dates:
        preceding = [d for d in buy_dates if d <= sell_dt]
        if preceding:
            d = sell_dt - preceding[-1]
            days = d.days if isinstance(d, timedelta) else d
            if days > max_days:
                max_days = days
    return max_days


def max_consecutive_wins(trades: pl.DataFrame) -> int:
    sells = _sell_trades(trades).sort("Datetime")
    if sells.is_empty():
        return 0
    wins = (sells["PnL"] > 0).to_list()
    max_streak = streak = 0
    for w in wins:
        if w:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def max_consecutive_losses(trades: pl.DataFrame) -> int:
    sells = _sell_trades(trades).sort("Datetime")
    if sells.is_empty():
        return 0
    losses = (sells["PnL"] <= 0).to_list()
    max_streak = streak = 0
    for l in losses:
        if l:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def average_daily_return(returns: pl.Series) -> float:
    return float(returns.mean() or 0.0)


def daily_return_std(returns: pl.Series) -> float:
    return float(returns.std() or 0.0)


def return_skewness(returns: pl.Series) -> float:
    if returns.len() < 3:
        return 0.0
    return float(returns.skew())


def return_kurtosis(returns: pl.Series) -> float:
    if returns.len() < 4:
        return 0.0
    return float(returns.kurtosis())


def value_at_risk(returns: pl.Series, level: float = 0.05) -> float:
    """Historical VaR at the given level (default 5%)."""
    if returns.is_empty():
        return 0.0
    return float(returns.quantile(level, "lower"))


def conditional_value_at_risk(returns: pl.Series, level: float = 0.05) -> float:
    """Expected shortfall below the VaR level."""
    if returns.is_empty():
        return 0.0
    var = value_at_risk(returns, level)
    tail = returns.filter(returns <= var)
    if tail.is_empty():
        return var
    return float(tail.mean())


def exposure_metric(equity: pl.DataFrame) -> float:
    """Fraction of bars with a non-zero position."""
    if "PositionValue" not in equity.columns:
        return 0.0
    n = equity.height
    if n == 0:
        return 0.0
    in_market = equity.filter(pl.col("PositionValue") > 0).height
    return in_market / n


def _sample_cov(x: pl.Series, y: pl.Series) -> float:
    """Sample covariance of two equal-length series."""
    n = x.len()
    if n < 2:
        return 0.0
    xm = x - x.mean()
    ym = y - y.mean()
    return float((xm * ym).sum() / (n - 1))


def _sample_var(x: pl.Series) -> float:
    n = x.len()
    if n < 2:
        return 0.0
    xm = x - x.mean()
    return float((xm * xm).sum() / (n - 1))


def beta(returns: pl.Series, benchmark_returns: pl.Series) -> float:
    """Beta against a benchmark return series."""
    if returns.len() < 2 or benchmark_returns.len() < 2:
        return 0.0
    min_len = min(returns.len(), benchmark_returns.len())
    r = returns.tail(min_len)
    b = benchmark_returns.tail(min_len)
    cov = _sample_cov(r, b)
    var = _sample_var(b)
    if var == 0:
        return 0.0
    return cov / var


def alpha(returns: pl.Series, benchmark_returns: pl.Series, risk_free_rate: float = 0.04) -> float:
    """Jensen's alpha."""
    b = beta(returns, benchmark_returns)
    ann_return = float(returns.mean() or 0.0) * TRADING_DAYS_PER_YEAR
    bench_return = float(benchmark_returns.mean() or 0.0) * TRADING_DAYS_PER_YEAR
    return ann_return - risk_free_rate - b * (bench_return - risk_free_rate)


def information_ratio(returns: pl.Series, benchmark_returns: pl.Series) -> float:
    min_len = min(returns.len(), benchmark_returns.len())
    r = returns.tail(min_len)
    b = benchmark_returns.tail(min_len)
    diff = r - b
    std = float(diff.std())
    if std == 0:
        return 0.0
    return float(diff.mean()) * math.sqrt(TRADING_DAYS_PER_YEAR) / std


def treynor_ratio(returns: pl.Series, benchmark_returns: pl.Series, risk_free_rate: float = 0.04) -> float:
    b = beta(returns, benchmark_returns)
    if b == 0:
        return 0.0
    ann_return = float(returns.mean() or 0.0) * TRADING_DAYS_PER_YEAR
    return (ann_return - risk_free_rate) / b


def monthly_returns(equity: pl.DataFrame) -> pl.DataFrame:
    """Monthly returns table for heatmap generation."""
    df = equity.with_columns(
        pl.col("Datetime").dt.strftime("%Y-%m").alias("Month"),
        pl.col("Datetime").dt.strftime("%Y").alias("Year"),
        pl.col("Datetime").dt.strftime("%m").alias("MonthNum"),
    )
    # First and last equity per month
    agg = (
        df.group_by("Month", "Year", "MonthNum")
        .agg([
            pl.col("TotalEquity").first().alias("start"),
            pl.col("TotalEquity").last().alias("end"),
        ])
        .with_columns(((pl.col("end") - pl.col("start")) / pl.col("start")).alias("return"))
        .sort("Year", "MonthNum")
    )
    return agg.select(["Year", "MonthNum", "return"])


def monthly_returns_heatmap(equity: pl.DataFrame) -> pl.DataFrame:
    """Pivot-style heatmap: years x months."""
    table = monthly_returns(equity)
    if table.is_empty():
        return pl.DataFrame()
    return table.pivot(index="Year", on="MonthNum", values="return").fill_null(0)


def drawdown_series(equity: pl.DataFrame) -> pl.Series:
    """Series of drawdown percentages at each point."""
    values = equity["TotalEquity"].to_list()
    peak = values[0] if values else 0.0
    dds = []
    for v in values:
        if v > peak:
            peak = v
        if peak:
            dds.append((peak - v) / peak)
        else:
            dds.append(0.0)
    return pl.Series("drawdown", dds)


def calculate_metrics(
    equity: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    risk_free_rate: float = 0.04,
    benchmark_returns: Optional[pl.Series] = None,
) -> Dict[str, Any]:
    """Compute a comprehensive set of backtest metrics."""
    logger.debug("calculate_metrics start")
    returns = _daily_returns(equity)

    metrics: Dict[str, Any] = {
        "total_return": total_return_metric(equity),
        "cagr": cagr(equity),
        "annualized_return": annualized_return(equity),
        "annualized_volatility": annualized_volatility(returns),
        "sharpe_ratio": sharpe_ratio(returns, risk_free_rate),
        "sortino_ratio": sortino_ratio(returns, risk_free_rate),
        "calmar_ratio": calmar_ratio(equity, risk_free_rate),
        "max_drawdown": max_drawdown_metric(equity),
        "max_drawdown_duration_days": max_drawdown_duration(equity),
        "avg_drawdown": avg_drawdown(equity),
        "ulcer_index": ulcer_index(equity),
        "recovery_factor": recovery_factor(equity),
        "win_rate": win_rate_metric(trades),
        "num_trades": num_trades_metric(trades),
        "num_winning_trades": num_winning_trades(trades),
        "num_losing_trades": num_losing_trades(trades),
        "gross_profit": gross_profit(trades),
        "gross_loss": gross_loss(trades),
        "net_profit": net_profit(trades),
        "total_fees": total_fees(trades),
        "profit_factor": profit_factor(trades),
        "avg_trade_return": avg_trade_return(trades),
        "avg_winning_trade": avg_winning_trade(trades),
        "avg_losing_trade": avg_losing_trade(trades),
        "payoff_ratio": payoff_ratio(trades),
        "trade_expectancy": trade_expectancy(trades),
        "avg_trade_duration_days": average_trade_duration(trades),
        "max_trade_duration_days": max_trade_duration(trades),
        "max_consecutive_wins": max_consecutive_wins(trades),
        "max_consecutive_losses": max_consecutive_losses(trades),
        "average_daily_return": average_daily_return(returns),
        "daily_return_std": daily_return_std(returns),
        "return_skewness": return_skewness(returns),
        "return_kurtosis": return_kurtosis(returns),
        "value_at_risk_5": value_at_risk(returns, 0.05),
        "conditional_value_at_risk_5": conditional_value_at_risk(returns, 0.05),
        "exposure": exposure_metric(equity),
    }

    if benchmark_returns is not None:
        metrics["beta"] = beta(returns, benchmark_returns)
        metrics["alpha"] = alpha(returns, benchmark_returns, risk_free_rate)
        metrics["information_ratio"] = information_ratio(returns, benchmark_returns)
        metrics["treynor_ratio"] = treynor_ratio(returns, benchmark_returns, risk_free_rate)
    else:
        metrics["beta"] = None
        metrics["alpha"] = None
        metrics["information_ratio"] = None
        metrics["treynor_ratio"] = None

    logger.debug("calculate_metrics done")
    return metrics
