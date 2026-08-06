"""SQLite index for backtest runs and factor rank snapshots."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import polars as pl

logger = logging.getLogger(__name__)


class SQLiteIndex:
    """SQLite Tier-1 index for backtest bundles and factor snapshots."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or Path.home() / ".quantmind" / "index.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(str(self.path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backtest_id TEXT UNIQUE,
                    name TEXT,
                    strategy_id TEXT,
                    symbols TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    total_return REAL,
                    max_drawdown REAL,
                    num_trades INTEGER,
                    win_rate REAL,
                    bundle_path TEXT,
                    parameters TEXT,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS factor_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    factor_name TEXT,
                    symbol TEXT,
                    value REAL,
                    rank INTEGER,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_factor_date_name
                ON factor_snapshots(date, factor_name)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_backtest_id
                ON backtest_runs(backtest_id)
                """
            )
            conn.commit()

    def insert_backtest(
        self,
        bundle_path: Path,
        result,
        strategy_id: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        backtest_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        """Index a backtest run stored on disk."""
        with sqlite3.connect(str(self.path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO backtest_runs
                (backtest_id, name, strategy_id, symbols, start_date, end_date,
                 total_return, max_drawdown, num_trades, win_rate, bundle_path,
                 parameters, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    backtest_id,
                    name,
                    strategy_id,
                    json.dumps(symbols or []),
                    None,
                    None,
                    result.total_return,
                    result.max_drawdown,
                    result.num_trades,
                    result.win_rate,
                    str(bundle_path),
                    json.dumps(getattr(result, "parameters", {}) or {}),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    def insert_factor_snapshot(
        self,
        snapshot_date: date,
        factor_name: str,
        df: pl.DataFrame,
    ) -> None:
        """Store a factor snapshot with cross-sectional ranks."""
        date_str = snapshot_date.isoformat()
        created_at = datetime.utcnow().isoformat()
        with sqlite3.connect(str(self.path)) as conn:
            # Clear existing snapshot for (date, factor_name)
            conn.execute(
                "DELETE FROM factor_snapshots WHERE date = ? AND factor_name = ?",
                (date_str, factor_name),
            )
            rows = df.select(["symbol", "value"]).to_dicts()
            sorted_rows = sorted(
                rows,
                key=lambda r: (r["value"] if r["value"] is not None else float("-inf")),
                reverse=True,
            )
            for rank, row in enumerate(sorted_rows, start=1):
                conn.execute(
                    """
                    INSERT INTO factor_snapshots
                    (date, factor_name, symbol, value, rank, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        date_str,
                        factor_name,
                        row["symbol"],
                        row["value"],
                        rank,
                        created_at,
                    ),
                )
            conn.commit()

    def query_backtests(
        self,
        strategy_id: Optional[str] = None,
        min_total_return: Optional[float] = None,
    ) -> pl.DataFrame:
        with sqlite3.connect(str(self.path)) as conn:
            sql = "SELECT * FROM backtest_runs WHERE 1=1"
            params: List[Any] = []
            if strategy_id:
                sql += " AND strategy_id = ?"
                params.append(strategy_id)
            if min_total_return is not None:
                sql += " AND total_return >= ?"
                params.append(min_total_return)
            sql += " ORDER BY created_at DESC"
            rows = conn.execute(sql, params).fetchall()
            cols = [d[0] for d in conn.execute(sql, params).description]
            return pl.DataFrame([dict(zip(cols, r)) for r in rows])


class RankIndex:
    """Convenience wrapper over :class:`SQLiteIndex` for top-N factor queries."""

    def __init__(self, index: Optional[SQLiteIndex] = None) -> None:
        self.index = index or SQLiteIndex()

    def get_top(
        self,
        snapshot_date: date,
        factor_name: str,
        n: int = 10,
    ) -> pl.DataFrame:
        """Return the top-``n`` symbols for a factor on a given date."""
        with sqlite3.connect(str(self.index.path)) as conn:
            rows = conn.execute(
                """
                SELECT symbol, value, rank
                FROM factor_snapshots
                WHERE date = ? AND factor_name = ?
                ORDER BY rank ASC
                LIMIT ?
                """,
                (snapshot_date.isoformat(), factor_name, n),
            ).fetchall()
            return pl.DataFrame(
                rows,
                schema=[("symbol", pl.Utf8), ("value", pl.Float64), ("rank", pl.Int64)],
                orient="row",
            )

    def snapshot_exists(self, snapshot_date: date, factor_name: str) -> bool:
        with sqlite3.connect(str(self.index.path)) as conn:
            row = conn.execute(
                "SELECT 1 FROM factor_snapshots WHERE date = ? AND factor_name = ? LIMIT 1",
                (snapshot_date.isoformat(), factor_name),
            ).fetchone()
            return row is not None
