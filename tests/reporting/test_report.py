from datetime import datetime, timedelta

import polars as pl

from quantmind.backtesting.result import BacktestResult
from quantmind.reporting import BacktestReport


def _make_result():
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(100)]
    equity = pl.DataFrame(
        {
            "Datetime": dates,
            "Cash": [50_000.0] * 100,
            "PositionValue": [50_000.0] * 100,
            "TotalEquity": [100_000.0 + i * 100 for i in range(100)],
        }
    )
    trades = pl.DataFrame(
        {
            "Datetime": [dates[10], dates[30], dates[60], dates[90]],
            "Symbol": ["RELIANCE"] * 4,
            "Side": ["BUY", "SELL", "BUY", "SELL"],
            "Price": [100.0, 110.0, 105.0, 115.0],
            "Quantity": [100.0, 100.0, 100.0, 100.0],
            "Fee": [10.0, 11.0, 10.0, 11.0],
            "PnL": [0.0, 989.0, 0.0, 989.0],
            "Reason": ["buy", "sell", "buy", "sell"],
        }
    )
    return BacktestResult(
        equity_curve=equity,
        trades=trades,
        total_return=0.09,
        max_drawdown=0.0,
        num_trades=2,
        win_rate=1.0,
        parameters={"strategy_id": "test"},
    )


def test_report_from_result():
    result = _make_result()
    report = BacktestReport.from_result(result, name="test-report")
    assert report.name == "test-report"
    assert report.metrics["num_trades"] == 2
    assert report.metrics["total_return"] > 0


def test_report_to_dict():
    result = _make_result()
    report = BacktestReport.from_result(result)
    d = report.to_dict()
    assert "metrics" in d
    assert "equity_curve" in d
    assert "monthly_heatmap" in d
    assert "drawdown" in d


def test_report_to_markdown():
    result = _make_result()
    report = BacktestReport.from_result(result)
    md = report.to_markdown()
    assert "Backtest Report" in md
    assert "Total Return" in md
    assert "Trades" in md


def test_report_to_html():
    result = _make_result()
    report = BacktestReport.from_result(result)
    html = report.to_html()
    assert "<html>" in html
    assert "Total Equity" in html or "Equity" in html
