"""Single-file backtest bundle persistence (.iafbt)."""

from __future__ import annotations

import json
import logging
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import polars as pl

from ..backtesting.result import BacktestResult, BacktestRun

logger = logging.getLogger(__name__)

BUNDLE_EXT = ".iafbt"
FORMAT_VERSION = 1


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, pl.DataFrame):
        raise TypeError("DataFrames must be stored as Parquet blobs")
    return value


def _result_to_metadata(result: BacktestResult) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "equity_curve_path": "equity_curve.parquet",
        "trades_path": "trades.parquet",
    }
    scalar_fields = [
        "total_return",
        "max_drawdown",
        "num_trades",
        "win_rate",
        "parameters",
    ]
    for field in scalar_fields:
        value = getattr(result, field, None)
        if value is None:
            continue
        meta[field] = _serialize_value(value)
    if isinstance(result, BacktestRun):
        meta["backtest_id"] = result.backtest_id
        meta["name"] = result.name
        meta["created_at"] = (
            result.created_at.isoformat() if result.created_at else None
        )
    return meta


def _result_from_metadata(meta: Dict[str, Any], zf: zipfile.ZipFile) -> BacktestResult:
    equity_bytes = zf.read(meta["equity_curve_path"])
    trades_bytes = zf.read(meta["trades_path"])
    equity_curve = pl.read_parquet(BytesIO(equity_bytes))
    trades = pl.read_parquet(BytesIO(trades_bytes))
    kwargs = {
        "equity_curve": equity_curve,
        "trades": trades,
        "total_return": float(meta.get("total_return", 0.0)),
        "max_drawdown": float(meta.get("max_drawdown", 0.0)),
        "num_trades": int(meta.get("num_trades", 0)),
        "win_rate": float(meta.get("win_rate", 0.0)),
        "parameters": meta.get("parameters", {}),
    }
    if meta.get("backtest_id") is not None or meta.get("name") is not None:
        created_at = meta.get("created_at")
        kwargs["backtest_id"] = meta.get("backtest_id")
        kwargs["name"] = meta.get("name")
        if created_at:
            kwargs["created_at"] = datetime.fromisoformat(created_at)
        return BacktestRun(**kwargs)
    return BacktestResult(**kwargs)


class BacktestBundle:
    """Wrapper around a saved backtest bundle."""

    def __init__(self, path: Union[str, Path], metadata: Dict[str, Any]) -> None:
        self.path = Path(path)
        self.metadata = metadata

    def load(self) -> BacktestResult:
        with zipfile.ZipFile(self.path, "r") as zf:
            return _result_from_metadata(self.metadata, zf)


def save_bundle(
    path: Union[str, Path],
    result: BacktestResult,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """Save a ``BacktestResult`` to ``.iafbt`` (zip with JSON + Parquet blobs)."""
    path = Path(path)
    if path.suffix != BUNDLE_EXT:
        path = path.with_suffix(BUNDLE_EXT)

    meta = _result_to_metadata(result)
    if extra_metadata:
        meta["extra"] = extra_metadata

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(meta, indent=2))
        for blob_path, df in [
            (meta["equity_curve_path"], result.equity_curve),
            (meta["trades_path"], result.trades),
        ]:
            buf = BytesIO()
            df.write_parquet(buf)
            zf.writestr(blob_path, buf.getvalue())

    logger.info("Saved backtest bundle to %s", path)
    return path


def load_bundle(
    path: Union[str, Path], summary_only: bool = False
) -> Union[BacktestBundle, BacktestResult]:
    """Load a backtest bundle. If ``summary_only`` return metadata wrapper."""
    path = Path(path)
    with zipfile.ZipFile(path, "r") as zf:
        metadata = json.loads(zf.read("metadata.json").decode())
    if summary_only:
        return BacktestBundle(path, metadata)
    with zipfile.ZipFile(path, "r") as zf:
        return _result_from_metadata(metadata, zf)
