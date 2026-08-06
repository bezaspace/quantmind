from datetime import datetime, timedelta

import polars as pl
import pytest

from quantmind.metrics.core import (
    calculate_metrics,
    cagr,
    drawdown_series,
    max_drawdown_metric,
    monthly_returns_heatmap,
    sharpe_ratio,
    total_return_metric,
)


def _equity(total_values, start_date=None):
    start = start_date or datetime(2023, 1, 1)
    dates = [start + timedelta(days=i) for i in range(len(total_values))]
    return pl.DataFrame({"Datetime": dates, "TotalEquity": total_values, "PositionValue": [0.0] * len(total_values)})


def test_total_return():
    eq = _equity([100.0, 110.0, 120.0])
    assert total_return_metric(eq) == pytest.approx(0.20, abs=1e-9)


def test_cagr_one_year():
    # 366 daily values spanning one year
    values = [100.0 + i * 20.0 / 365 for i in range(366)]
    eq = _equity(values, start_date=datetime(2023, 1, 1))
    assert cagr(eq) == pytest.approx(0.20, abs=1e-4)


def test_cagr_two_years():
    # 731 daily values spanning two years, doubling
    values = [100.0 + i * 44.0 / 730 for i in range(731)]
    eq = _equity(values, start_date=datetime(2023, 1, 1))
    assert cagr(eq) == pytest.approx(0.20, abs=1e-4)


def test_max_drawdown():
    eq = _equity([100.0, 110.0, 90.0, 120.0])
    assert max_drawdown_metric(eq) == pytest.approx((110 - 90) / 110, abs=1e-9)


def test_drawdown_series():
    eq = _equity([100.0, 110.0, 90.0, 120.0])
    dd = drawdown_series(eq)
    assert dd.to_list() == pytest.approx([0.0, 0.0, (110 - 90) / 110, 0.0], abs=1e-9)


def test_sharpe_no_volatility():
    # Geometric progression gives constant daily percentage returns
    eq = _equity([100.0, 110.0, 121.0, 133.1])
    returns = eq["TotalEquity"].pct_change().drop_nulls()
    assert sharpe_ratio(returns, risk_free_rate=0.0) == pytest.approx(0.0, abs=1e-6)


def test_calculate_metrics_basic():
    eq = _equity([100.0, 90.0, 110.0, 120.0])
    trades = pl.DataFrame(
        {
            "Datetime": [datetime(2023, 1, i) for i in range(2, 5)],
            "Symbol": ["RELIANCE"] * 3,
            "Side": ["SELL", "SELL", "SELL"],
            "Price": [100.0, 100.0, 100.0],
            "Quantity": [1.0, 1.0, 1.0],
            "Fee": [0.0, 0.0, 0.0],
            "PnL": [10.0, -5.0, 15.0],
            "Reason": ["sell"] * 3,
        }
    )
    metrics = calculate_metrics(eq, trades)
    assert metrics["total_return"] == pytest.approx(0.20, abs=1e-9)
    assert metrics["win_rate"] == pytest.approx(2 / 3, abs=1e-9)
    assert metrics["num_trades"] == 3
    assert metrics["profit_factor"] == pytest.approx(25 / 5, abs=1e-9)
    assert metrics["max_drawdown"] > 0


def test_monthly_heatmap():
    dates = [datetime(2023, 1, 1) + timedelta(days=10 * i) for i in range(10)]
    values = [100.0] * 5 + [110.0] * 5
    eq = pl.DataFrame({"Datetime": dates, "TotalEquity": values, "PositionValue": [0.0] * 10})
    heatmap = monthly_returns_heatmap(eq)
    assert not heatmap.is_empty()
    assert "2023" in heatmap["Year"].to_list()
