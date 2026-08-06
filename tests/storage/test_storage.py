from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import pytest

from quantmind.backtesting import VectorBacktest
from quantmind.domain import DataSource, Interval, PositionSize, TradingStrategy
from quantmind.domain.models import TimeUnit
from quantmind.storage import RankIndex, SQLiteIndex, Tier1Store, load_bundle, save_bundle
from quantmind.storage.bundle import BUNDLE_EXT


def _result():
    equity = pl.DataFrame(
        {
            "Datetime": [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)],
            "Equity": [1000.0, 1100.0, 1050.0],
        }
    )
    trades = pl.DataFrame(
        {
            "Datetime": [date(2023, 1, 1)],
            "Symbol": ["SYM"],
            "Side": ["BUY"],
            "Price": [100.0],
            "Quantity": [10.0],
            "Fee": [0.0],
            "PnL": [0.0],
            "Reason": ["buy_signal"],
        }
    )
    from quantmind.backtesting.result import BacktestResult

    return BacktestResult(
        equity_curve=equity,
        trades=trades,
        total_return=0.05,
        max_drawdown=0.05,
        num_trades=1,
        win_rate=1.0,
    )


def test_save_and_load_bundle():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "run"
        result = _result()
        bundle_path = save_bundle(path, result)
        assert bundle_path.suffix == BUNDLE_EXT
        loaded = load_bundle(bundle_path)
        assert loaded.total_return == pytest.approx(0.05)
        assert loaded.trades.height == 1


def test_load_bundle_summary_only():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "run"
        result = _result()
        bundle_path = save_bundle(path, result)
        summary = load_bundle(bundle_path, summary_only=True)
        assert summary.metadata["total_return"] == pytest.approx(0.05)
        assert "trades_path" in summary.metadata


def test_tier1_store():
    with TemporaryDirectory() as tmp:
        store = Tier1Store(Path(tmp) / "tier1")
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        digest = store.put(df, kind="test", key="foo")
        loaded = store.get(digest)
        assert loaded is not None
        assert loaded.equals(df)


def test_sqlite_index_insert_and_query():
    with TemporaryDirectory() as tmp:
        index = SQLiteIndex(Path(tmp) / "index.sqlite")
        result = _result()
        bundle_path = Path(tmp) / "run.iafbt"
        index.insert_backtest(
            bundle_path,
            result,
            strategy_id="TEST",
            symbols=["RELIANCE"],
            backtest_id="bt-1",
            name="test run",
        )
        rows = index.query_backtests(strategy_id="TEST")
        assert rows.height == 1
        assert rows[0, "total_return"] == pytest.approx(0.05)


def test_rank_index():
    with TemporaryDirectory() as tmp:
        index = SQLiteIndex(Path(tmp) / "index.sqlite")
        snapshot = pl.DataFrame(
            {"symbol": ["A", "B", "C"], "value": [0.3, 0.1, 0.2]}
        )
        index.insert_factor_snapshot(date(2023, 1, 4), "mom", snapshot)
        rank_index = RankIndex(index)
        top = rank_index.get_top(date(2023, 1, 4), "mom", n=2)
        assert top.height == 2
        assert top[0, "symbol"] == "A"
        assert top[1, "symbol"] == "C"
        assert top[0, "rank"] == 1


def test_bundle_with_backtest_run_round_trip():
    from quantmind.backtesting.result import BacktestRun

    run = BacktestRun(
        equity_curve=_result().equity_curve,
        trades=_result().trades,
        total_return=0.1,
        max_drawdown=0.02,
        num_trades=2,
        win_rate=0.5,
        backtest_id="run-42",
        name="answer",
    )
    with TemporaryDirectory() as tmp:
        path = save_bundle(Path(tmp) / "run", run)
        loaded = load_bundle(path)
        assert loaded.backtest_id == "run-42"
        assert loaded.name == "answer"
        assert loaded.total_return == pytest.approx(0.1)
