"""Intraday execution scheduler for live and paper trading."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Optional

from ..broker import BrokerClient, OrderRequest, OrderSide, OrderType
from ..broker.executor import PaperTradingExecutor
from ..data.providers import DataProvider, UpstoxDataProvider
from ..domain.calendar import TradingCalendar

logger = logging.getLogger(__name__)


@dataclass
class SchedulerConfig:
    symbols: list[str]
    interval: str = "1minute"
    sleep_seconds: int = 60
    market_open_ist: tuple[int, int] = (9, 15)
    market_close_ist: tuple[int, int] = (15, 30)
    max_orders_per_symbol: int = 10


@dataclass
class IntradayScheduler:
    """Run a strategy signal on every bar during market hours.

    The scheduler is intentionally simple: it fetches the latest bar for each
    symbol, calls a user-supplied ``signal_fn`` that returns BUY/SELL/HOLD, and
    routes the resulting order through a ``PaperTradingExecutor`` (default) or
    any ``BrokerClient``.
    """

    config: SchedulerConfig
    executor: PaperTradingExecutor
    calendar: TradingCalendar = field(default_factory=TradingCalendar)
    signal_fn: Optional[Callable[[str, Dict[str, Any]], Optional[str]]] = None
    data_provider: Optional[DataProvider] = None

    def __post_init__(self) -> None:
        if self.data_provider is None:
            self.data_provider = UpstoxDataProvider()
        self._orders_today: Dict[str, int] = {}

    def is_market_open(self, now: Optional[datetime] = None) -> bool:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Asia/Kolkata")
        now = now or datetime.now(tz)
        if not self.calendar.is_trading_day(now.date()):
            return False
        open_t, close_t = self.calendar.market_hours(now.date())
        return open_t <= now <= close_t

    def fetch_latest_bar(self, symbol: str) -> Dict[str, Any]:
        df = self.data_provider.get_ohlcv(symbol, self.config.interval)
        if df.height == 0:
            return {}
        return {col: df[col][-1] for col in df.columns}

    def run_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        bar = self.fetch_latest_bar(symbol)
        if not bar:
            logger.warning("No bar data for %s", symbol)
            return None

        signal = self.signal_fn(symbol, bar) if self.signal_fn else None
        if signal not in ("BUY", "SELL"):
            return None

        if self._orders_today.get(symbol, 0) >= self.config.max_orders_per_symbol:
            logger.info("Max orders reached for %s", symbol)
            return None

        side = OrderSide.BUY if signal == "BUY" else OrderSide.SELL
        order = self.executor.place_order(
            OrderRequest(
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=1,
                product="MIS",
            )
        )
        # Fill market order immediately using the latest bar close
        close = bar.get("Close")
        if close is not None and order.status.value in ("OPEN", "PENDING"):
            from datetime import datetime as _dt
            self.executor.process_market(_dt.utcnow(), {symbol: float(close)})

        self._orders_today[symbol] = self._orders_today.get(symbol, 0) + 1
        return {"symbol": symbol, "signal": signal, "order": order}

    def run(self, duration_seconds: Optional[int] = None) -> None:
        """Blocking loop that runs while the market is open."""
        start = time.time()
        while True:
            if duration_seconds and (time.time() - start) > duration_seconds:
                break
            if not self.is_market_open():
                logger.info("Market closed; waiting...")
                time.sleep(self.config.sleep_seconds)
                continue

            for symbol in self.config.symbols:
                try:
                    self.run_tick(symbol)
                except Exception:
                    logger.exception("Tick failed for %s", symbol)

            time.sleep(self.config.sleep_seconds)
