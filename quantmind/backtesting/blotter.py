"""Event-driven order execution engine / blotter."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import polars as pl

from ..domain.order import Order, OrderSide, OrderStatus, OrderType
from .costs import CostBreakdown, IndianEquityCostModel

logger = logging.getLogger(__name__)


@dataclass
class Fill:
    """Result of a simulated fill."""

    order: Order
    fill_price: float
    quantity: float
    fees: float
    cost_breakdown: Optional[CostBreakdown] = None
    slippage: float = 0.0
    bar_time: Optional[datetime] = None


@dataclass
class Position:
    """Track holdings for a symbol."""

    symbol: str
    quantity: float = 0.0
    average_cost: float = 0.0

    def market_value(self, price: float) -> float:
        return self.quantity * price

    def buy(self, quantity: float, price: float) -> None:
        if quantity <= 0:
            return
        total_cost = self.quantity * self.average_cost + quantity * price
        self.quantity += quantity
        self.average_cost = total_cost / self.quantity if self.quantity else 0.0

    def sell(self, quantity: float) -> None:
        if quantity <= self.quantity:
            self.quantity -= quantity
        else:
            self.quantity = 0.0
        if self.quantity == 0:
            self.average_cost = 0.0


@dataclass
class Portfolio:
    """Cash + positions state."""

    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)

    def position(self, symbol: str) -> Position:
        sym = symbol.upper()
        if sym not in self.positions:
            self.positions[sym] = Position(symbol=sym)
        return self.positions[sym]

    def total_value(self, prices: Dict[str, float]) -> float:
        value = self.cash
        for sym, pos in self.positions.items():
            value += pos.market_value(prices.get(sym, 0.0))
        return value


class ExecutionEngine:
    """Matches orders against OHLCV bars and applies cost/slippage."""

    def __init__(
        self,
        cost_model: Optional[IndianEquityCostModel] = None,
        long_only: bool = True,
    ):
        self.cost_model = cost_model or IndianEquityCostModel()
        self.long_only = long_only
        self.pending_orders: List[Order] = []
        self.fills: List[Fill] = []

    def submit(self, order: Order) -> None:
        if order.status != OrderStatus.CREATED:
            return
        order.status = OrderStatus.OPEN
        self.pending_orders.append(order)
        logger.debug("Submitted %s order for %s", order.side.value, order.symbol)

    def cancel(self, order: Order) -> None:
        if order in self.pending_orders:
            self.pending_orders.remove(order)
        order.status = OrderStatus.CANCELLED

    def process_bar(
        self,
        bar_time: datetime,
        ohlcv: Dict[str, Dict[str, float]],
    ) -> List[Fill]:
        """Evaluate pending orders against the current bar's OHLCV."""
        fills = []
        still_pending = []
        for order in self.pending_orders:
            bar = ohlcv.get(order.symbol)
            if not bar:
                still_pending.append(order)
                continue
            fill = self._try_fill(order, bar_time, bar)
            if fill is None:
                still_pending.append(order)
            else:
                fills.append(fill)
        self.pending_orders = still_pending
        self.fills.extend(fills)
        return fills

    def _try_fill(
        self,
        order: Order,
        bar_time: datetime,
        bar: Dict[str, float],
    ) -> Optional[Fill]:
        open_p = float(bar.get("Open", 0.0))
        high = float(bar.get("High", 0.0))
        low = float(bar.get("Low", 0.0))
        close = float(bar.get("Close", 0.0))

        if order.order_type == OrderType.MARKET:
            # Fill at next bar's open (open_p)
            fill_price, net_value, cost = self.cost_model.apply_buy(
                open_p, order.quantity
            ) if order.side == OrderSide.BUY else self.cost_model.apply_sell(
                open_p, order.quantity
            )
            return self._create_fill(order, fill_price, net_value, cost, bar_time)

        if order.order_type == OrderType.LIMIT and order.price is not None:
            if order.side == OrderSide.BUY and low <= order.price:
                base = min(order.price, close)
            elif order.side == OrderSide.SELL and high >= order.price:
                base = max(order.price, close)
            else:
                return None
            fill_price, net_value, cost = self.cost_model.apply_buy(
                base, order.quantity
            ) if order.side == OrderSide.BUY else self.cost_model.apply_sell(
                base, order.quantity
            )
            return self._create_fill(order, fill_price, net_value, cost, bar_time)

        if order.order_type == OrderType.STOP and order.stop_price is not None:
            if order.side == OrderSide.BUY and high >= order.stop_price:
                base = order.stop_price
            elif order.side == OrderSide.SELL and low <= order.stop_price:
                base = order.stop_price
            else:
                return None
            fill_price, net_value, cost = self.cost_model.apply_buy(
                base, order.quantity
            ) if order.side == OrderSide.BUY else self.cost_model.apply_sell(
                base, order.quantity
            )
            return self._create_fill(order, fill_price, net_value, cost, bar_time)

        # STOP_LIMIT: trigger first, then limit fill
        if order.order_type == OrderType.STOP_LIMIT:
            sp = order.stop_price
            lp = order.price
            if sp is None or lp is None:
                return None
            if order.side == OrderSide.BUY and high >= sp and low <= lp:
                base = lp
            elif order.side == OrderSide.SELL and low <= sp and high >= lp:
                base = lp
            else:
                return None
            fill_price, net_value, cost = self.cost_model.apply_buy(
                base, order.quantity
            ) if order.side == OrderSide.BUY else self.cost_model.apply_sell(
                base, order.quantity
            )
            return self._create_fill(order, fill_price, net_value, cost, bar_time)

        return None

    def _create_fill(
        self,
        order: Order,
        fill_price: float,
        net_value: float,
        cost: CostBreakdown,
        bar_time: datetime,
    ) -> Fill:
        order.fill_price = fill_price
        order.fees = cost.total
        order.slippage = self.cost_model.slippage_pct
        order.status = OrderStatus.CLOSED
        order.filled_at = bar_time
        return Fill(
            order=order,
            fill_price=fill_price,
            quantity=order.quantity,
            fees=cost.total,
            cost_breakdown=cost,
            slippage=self.cost_model.slippage_pct,
            bar_time=bar_time,
        )

    def apply_fill(self, fill: Fill, portfolio: Portfolio) -> float:
        """Update portfolio for a fill and return realized PnL (0 for buys)."""
        order = fill.order
        symbol = order.symbol.upper()
        position = portfolio.position(symbol)

        if order.side == OrderSide.BUY:
            portfolio.cash -= (fill.fill_price * fill.quantity) + fill.fees
            position.buy(fill.quantity, fill.fill_price)
            return 0.0

        # SELL
        avg_cost = position.average_cost
        portfolio.cash += (fill.fill_price * fill.quantity) - fill.fees
        realized_pnl = (fill.fill_price - avg_cost) * fill.quantity if position.quantity else 0.0
        position.sell(fill.quantity)
        return realized_pnl
