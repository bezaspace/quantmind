"""Built-in tools exposed to the QuantMind agent."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import polars as pl

from ..backtesting import VectorBacktest
from ..data.providers import UpstoxDataProvider
from ..pipeline import run_pipeline
from ..pipeline.factors.builtin import Latest, Returns
from ..pipeline.panel import dict_to_long_form
from ..storage import save_bundle
from .core import Tool, ToolResult

logger = logging.getLogger(__name__)


async def get_ohlcv(symbol: str, interval: str = "day", start: str = "", end: str = "") -> ToolResult:
    """Fetch OHLCV data for a symbol."""
    try:
        df = UpstoxDataProvider().get_ohlcv(
            symbol,
            interval,
            start=start or None,
            end=end or None,
        )
        return ToolResult(
            True,
            {
                "symbol": symbol,
                "interval": interval,
                "rows": df.height,
                "start": str(df["Datetime"].min()) if df.height else None,
                "end": str(df["Datetime"].max()) if df.height else None,
            },
        )
    except Exception as exc:
        logger.exception("get_ohlcv failed")
        return ToolResult(False, None, str(exc))


async def run_backtest(symbol: str, fast_period: int = 20, slow_period: int = 50) -> ToolResult:
    """Run a simple MA-crossover vector backtest on a symbol."""
    try:
        from examples.moving_average_crossover import MovingAverageCrossoverStrategy

        df = UpstoxDataProvider().get_ohlcv(symbol, "day", start="2019-08-06", end="2024-08-06")
        strategy = MovingAverageCrossoverStrategy(
            symbol=symbol,
            fast_period=int(fast_period),
            slow_period=int(slow_period),
        )
        result = VectorBacktest(
            strategy,
            {f"{symbol}_day": df},
            initial_capital=1_000_000,
        ).run()
        return ToolResult(
            True,
            {
                "total_return": result.total_return,
                "max_drawdown": result.max_drawdown,
                "num_trades": result.num_trades,
                "win_rate": result.win_rate,
            },
        )
    except Exception as exc:
        logger.exception("run_backtest failed")
        return ToolResult(False, None, str(exc))


async def run_pipeline_rank(symbols: str, factor: str = "returns", window: int = 5, top_n: int = 5) -> ToolResult:
    """Rank a comma-separated list of symbols by a factor."""
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        data = {}
        for sym in symbol_list:
            df = UpstoxDataProvider().get_ohlcv(sym, "day", start="2023-01-01")
            data[sym] = df
        panel = dict_to_long_form(data)

        from ..pipeline.pipeline import Pipeline

        class RankPipeline(Pipeline):
            latest = Latest("close")
            returns = Returns(window=int(window))
            rank = returns.rank()

        result = run_pipeline(panel, RankPipeline)
        # Keep only last date and top_n
        last_date = result["datetime"].max()
        top = (
            result.filter(pl.col("datetime") == last_date)
            .filter(pl.col("rank").is_not_null())
            .sort("rank")
            .head(int(top_n))
        )
        return ToolResult(True, {"date": str(last_date), "ranking": top.to_dicts()})
    except Exception as exc:
        logger.exception("run_pipeline_rank failed")
        return ToolResult(False, None, str(exc))


async def get_metrics(equity_curve_json: str) -> ToolResult:
    """Compute core metrics from a JSON equity curve."""
    try:
        from ..metrics.core import (
            annualized_volatility,
            cagr,
            max_drawdown_metric,
            sharpe_ratio,
            total_return_metric,
        )

        records = json.loads(equity_curve_json)
        df = pl.DataFrame(records)
        if "TotalEquity" not in df.columns:
            return ToolResult(False, None, "equity curve must contain 'TotalEquity'")
        returns = df["TotalEquity"].pct_change().drop_nulls()
        summary = {
            "total_return": total_return_metric(df),
            "cagr": cagr(df),
            "max_drawdown": max_drawdown_metric(df),
            "sharpe_ratio": sharpe_ratio(returns),
            "annualized_volatility": annualized_volatility(returns),
        }
        return ToolResult(True, summary)
    except Exception as exc:
        logger.exception("get_metrics failed")
        return ToolResult(False, None, str(exc))


async def save_backtest_bundle(path: str, result_json: str) -> ToolResult:
    """Save a backtest result as an .iafbt bundle."""
    try:
        from ..backtesting.result import BacktestResult
        import polars as pl

        payload = json.loads(result_json)
        result = BacktestResult(
            equity_curve=pl.DataFrame(payload["equity_curve"]),
            trades=pl.DataFrame(payload["trades"]),
            total_return=payload["total_return"],
            max_drawdown=payload["max_drawdown"],
            num_trades=payload["num_trades"],
            win_rate=payload["win_rate"],
            parameters=payload.get("parameters", {}),
        )
        bundle_path = save_bundle(path, result)
        return ToolResult(True, {"bundle_path": str(bundle_path)})
    except Exception as exc:
        logger.exception("save_backtest_bundle failed")
        return ToolResult(False, None, str(exc))


TOOLS = [
    Tool(
        name="get_ohlcv",
        description="Fetch OHLCV market data for a symbol.",
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "interval": {"type": "string", "default": "day"},
                "start": {"type": "string", "default": ""},
                "end": {"type": "string", "default": ""},
            },
            "required": ["symbol"],
        },
        handler=get_ohlcv,
    ),
    Tool(
        name="run_backtest",
        description="Run a moving-average crossover backtest on a symbol and return summary metrics.",
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "fast_period": {"type": "integer", "default": 20},
                "slow_period": {"type": "integer", "default": 50},
            },
            "required": ["symbol"],
        },
        handler=run_backtest,
        requires_approval=False,
    ),
    Tool(
        name="run_pipeline_rank",
        description="Rank a comma-separated list of symbols by a short-term momentum factor.",
        parameters={
            "type": "object",
            "properties": {
                "symbols": {"type": "string"},
                "factor": {"type": "string", "default": "returns"},
                "window": {"type": "integer", "default": 5},
                "top_n": {"type": "integer", "default": 5},
            },
            "required": ["symbols"],
        },
        handler=run_pipeline_rank,
    ),
    Tool(
        name="get_metrics",
        description="Compute QuantMind metrics from a JSON equity curve.",
        parameters={
            "type": "object",
            "properties": {
                "equity_curve_json": {"type": "string"},
            },
            "required": ["equity_curve_json"],
        },
        handler=get_metrics,
    ),
    Tool(
        name="save_backtest_bundle",
        description="Save a backtest result as a .iafbt bundle file.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "result_json": {"type": "string"},
            },
            "required": ["path", "result_json"],
        },
        handler=save_backtest_bundle,
        requires_approval=True,
    ),
]


def get_tool(name: str) -> Tool:
    for tool in TOOLS:
        if tool.name == name:
            return tool
    raise KeyError(name)
