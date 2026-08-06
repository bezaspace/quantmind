"""Content-addressed OHLCV cache with a SQLite index."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import polars as pl


class OHLCVCache:
    """Content-addressed cache for OHLCV data.

    Each query (provider, symbol, interval, start, end) is hashed and the
    resulting Polars DataFrame is stored as a Parquet blob. An SQLite index
    maps the query dimensions to the hash so the same request never downloads
    the same data twice.
    """

    def __init__(self, cache_dir: Optional[str | Path] = None):
        if cache_dir is None:
            cache_dir = Path.home() / ".quantmind" / "cache"
        self.cache_dir = Path(cache_dir)
        self.ohlcv_dir = self.cache_dir / "ohlcv"
        self.ohlcv_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / "ohlcv_index.db"
        self._init_index()

    def _init_index(self) -> None:
        with sqlite3.connect(self.index_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ohlcv_cache (
                    provider TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    rows INTEGER,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (provider, symbol, interval, start_date, end_date)
                )
                """
            )
            conn.commit()

    def get(
        self,
        provider: str,
        symbol: str,
        interval: str,
        start: Optional[date | datetime],
        end: Optional[date | datetime],
    ) -> Optional[pl.DataFrame]:
        """Return a cached DataFrame if it exists."""
        key = self._hash_query(provider, symbol, interval, start, end)
        file_path = self.ohlcv_dir / f"{key}.parquet"
        if not file_path.exists():
            return None
        try:
            return pl.read_parquet(file_path)
        except Exception:
            return None

    def set(
        self,
        provider: str,
        symbol: str,
        interval: str,
        start: Optional[date | datetime],
        end: Optional[date | datetime],
        data: pl.DataFrame,
    ) -> str:
        """Persist a DataFrame and update the index."""
        key = self._hash_query(provider, symbol, interval, start, end)
        file_path = self.ohlcv_dir / f"{key}.parquet"
        data.write_parquet(file_path)

        with sqlite3.connect(self.index_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ohlcv_cache
                (provider, symbol, interval, start_date, end_date, hash, rows, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    symbol.upper(),
                    interval,
                    self._fmt_date(start),
                    self._fmt_date(end),
                    key,
                    len(data),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        return key

    def has(
        self,
        provider: str,
        symbol: str,
        interval: str,
        start: Optional[date | datetime],
        end: Optional[date | datetime],
    ) -> bool:
        key = self._hash_query(provider, symbol, interval, start, end)
        return (self.ohlcv_dir / f"{key}.parquet").exists()

    def clear(self) -> None:
        """Delete all cached blobs and the index."""
        for f in self.ohlcv_dir.glob("*.parquet"):
            f.unlink()
        if self.index_path.exists():
            self.index_path.unlink()
        self._init_index()

    @staticmethod
    def _hash_query(
        provider: str,
        symbol: str,
        interval: str,
        start: Optional[date | datetime],
        end: Optional[date | datetime],
    ) -> str:
        payload = {
            "provider": provider,
            "symbol": symbol.upper(),
            "interval": interval,
            "start": OHLCVCache._fmt_date(start),
            "end": OHLCVCache._fmt_date(end),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _fmt_date(d: Optional[date | datetime | str]) -> str:
        if d is None:
            return ""
        if isinstance(d, str):
            d = date.fromisoformat(d)
        if isinstance(d, datetime):
            return d.date().isoformat()
        return d.isoformat()
