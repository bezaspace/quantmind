"""Built-in tools exposed to the QuantMind agent."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import polars as pl

from ..audit import get_audit_logger
from ..backtesting import VectorBacktest
from ..broker import OrderRequest, OrderSide, OrderType, PaperTradingExecutor
from ..broker.upstox_client import UpstoxBrokerClient
from ..config import get_settings
from ..data.providers import UpstoxDataProvider
from ..derivatives import get_option_chain
from ..execution import IntradayScheduler, SchedulerConfig
from ..indicators.core import ema, sma
from ..pipeline import run_pipeline
from ..pipeline.factors.builtin import Latest, Returns
from ..pipeline.panel import dict_to_long_form
from ..risk import RiskController
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


_PAPER_EXECUTOR: PaperTradingExecutor | None = None


def _get_paper_executor() -> PaperTradingExecutor:
    global _PAPER_EXECUTOR
    if _PAPER_EXECUTOR is None:
        settings = get_settings()
        _PAPER_EXECUTOR = PaperTradingExecutor(
            initial_capital=1_000_000.0,
            client=UpstoxBrokerClient(paper=True),
            risk_controller=RiskController(
                max_order_quantity=settings.max_order_quantity,
                max_daily_loss_pct=settings.max_daily_loss_pct,
                allowed_products=settings.allowed_products.split(","),
                long_only=True,
            ),
        )
    return _PAPER_EXECUTOR


async def place_paper_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "MARKET",
    price: float = 0.0,
    product: str = "CNC",
) -> ToolResult:
    """Place a paper order on the Upstox sandbox (or local simulation if no credentials)."""
    try:
        executor = _get_paper_executor()
        req = OrderRequest(
            symbol=symbol,
            side=OrderSide(side.upper()),
            order_type=OrderType(order_type.upper()),
            quantity=float(quantity),
            price=float(price) if price else None,
            product=product,
        )
        order = executor.place_order(req)
        # In paper mode, immediately try to fill against the latest close price
        from datetime import datetime

        prices = executor._latest_prices([symbol])
        if prices:
            executor.process_market(datetime.utcnow(), prices)

        audit = get_audit_logger()
        audit.log(
            action="place_paper_order",
            payload={
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "order_type": order_type,
                "status": order.status.value,
                "order_id": order.order_id,
                "message": order.message,
            },
        )

        if order.status not in (OrderStatus.COMPLETE, OrderStatus.OPEN):
            return ToolResult(False, None, order.message or "Order rejected")

        return ToolResult(
            True,
            {
                "order_id": order.order_id,
                "status": order.status.value,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "message": order.message,
            },
        )
    except Exception as exc:
        logger.exception("place_paper_order failed")
        return ToolResult(False, None, str(exc))


async def get_paper_portfolio() -> ToolResult:
    """Return the current paper trading portfolio summary."""
    try:
        executor = _get_paper_executor()
        summary = executor.summary()
        return ToolResult(True, summary)
    except Exception as exc:
        logger.exception("get_paper_portfolio failed")
        return ToolResult(False, None, str(exc))


async def get_paper_pnl(symbols: str = "") -> ToolResult:
    """Return paper trading P&L for the given comma-separated symbols."""
    try:
        executor = _get_paper_executor()
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if not symbol_list:
            symbol_list = list(executor.portfolio.positions.keys())
        prices = executor._latest_prices(symbol_list)
        pnl = executor.get_pnl(prices)
        return ToolResult(
            True,
            {
                "realized": pnl.realized,
                "unrealized": pnl.unrealized,
                "fees": pnl.fees,
                "total": pnl.total,
                "prices": prices,
            },
        )
    except Exception as exc:
        logger.exception("get_paper_pnl failed")
        return ToolResult(False, None, str(exc))


async def get_option_chain(symbol: str) -> ToolResult:
    """Return an option chain for an underlying symbol (synthetic if market data unavailable)."""
    try:
        chain = get_option_chain(symbol)
        return ToolResult(
            True,
            {
                "underlying": symbol,
                "contracts": [
                    {
                        "symbol": c.symbol,
                        "expiry": c.expiry.isoformat(),
                        "strike": c.strike,
                        "option_type": c.option_type.value,
                    }
                    for c in chain[:10]
                ],
            },
        )
    except Exception as exc:
        logger.exception("get_option_chain failed")
        return ToolResult(False, None, str(exc))


async def run_intraday_signal(symbol: str, fast: int = 5, slow: int = 10) -> ToolResult:
    """Fetch the latest 1-minute bars and emit a BUY/SELL/HOLD signal based on SMA crossover."""
    try:
        provider = UpstoxDataProvider()
        df = provider.get_ohlcv(symbol, "1minute")
        if df.height < slow:
            return ToolResult(False, None, "Not enough 1m data")
        df = sma(df, fast, column="Close", result_column="fast")
        df = sma(df, slow, column="Close", result_column="slow")
        fast_val = float(df["fast"][-1])
        slow_val = float(df["slow"][-1])
        prev_fast = float(df["fast"][-2])
        prev_slow = float(df["slow"][-2])

        signal = "HOLD"
        if prev_fast <= prev_slow and fast_val > slow_val:
            signal = "BUY"
        elif prev_fast >= prev_slow and fast_val < slow_val:
            signal = "SELL"

        return ToolResult(
            True,
            {
                "symbol": symbol,
                "signal": signal,
                "fast": fast_val,
                "slow": slow_val,
                "price": float(df["Close"][-1]),
            },
        )
    except Exception as exc:
        logger.exception("run_intraday_signal failed")
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
        name="place_paper_order",
        description="Place a paper trading order (Upstox sandbox / local simulation).",
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["BUY", "SELL"]},
                "quantity": {"type": "number"},
                "order_type": {"type": "string", "enum": ["MARKET", "LIMIT", "STOP"], "default": "MARKET"},
                "price": {"type": "number", "default": 0},
                "product": {"type": "string", "default": "CNC"},
            },
            "required": ["symbol", "side", "quantity"],
        },
        handler=place_paper_order,
        requires_approval=True,
    ),
    Tool(
        name="get_paper_portfolio",
        description="Return the current paper trading portfolio summary.",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=get_paper_portfolio,
    ),
    Tool(
        name="get_paper_pnl",
        description="Return paper trading P&L for the given comma-separated symbols.",
        parameters={
            "type": "object",
            "properties": {
                "symbols": {"type": "string", "default": ""},
            },
        },
        handler=get_paper_pnl,
    ),
    Tool(
        name="get_option_chain",
        description="Return an option chain for an underlying symbol.",
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
            },
            "required": ["symbol"],
        },
        handler=get_option_chain,
    ),
    Tool(
        name="run_intraday_signal",
        description="Fetch the latest 1-minute bars and emit a BUY/SELL/HOLD SMA-crossover signal.",
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "fast": {"type": "integer", "default": 5},
                "slow": {"type": "integer", "default": 10},
            },
            "required": ["symbol"],
        },
        handler=run_intraday_signal,
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
