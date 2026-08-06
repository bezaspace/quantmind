"""Paper trading executor that fills orders against market data."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import polars as pl

from ..backtesting.costs import IndianEquityCostModel
from ..data.providers import UpstoxDataProvider
from .order import OrderRequest, OrderResponse, OrderSide, OrderStatus, OrderType
from .portfolio import PnL, PortfolioTracker, Position
from .upstox_client import UpstoxBrokerClient

logger = logging.getLogger(__name__)


@dataclass
class Fill:
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fees: float
    timestamp: datetime


@dataclass
class PaperTradingExecutor:
    """Simulates order execution using delayed-market fills."""

    initial_capital: float = 1_000_000.0
    cost_model: IndianEquityCostModel = field(
        default_factory=lambda: IndianEquityCostModel()
    )
    client: Optional[UpstoxBrokerClient] = None
    data_provider: Optional[UpstoxDataProvider] = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = UpstoxBrokerClient(paper=True)
        if self.data_provider is None:
            self.data_provider = UpstoxDataProvider()
        self.portfolio = PortfolioTracker(cash=self.initial_capital)
        self.pending_orders: Dict[str, OrderResponse] = {}
        self.orders: List[OrderResponse] = []
        self.fills: List[Fill] = []

    def place_order(self, request: OrderRequest) -> OrderResponse:
        response = self.client.place_order(request)
        if response.status in (OrderStatus.OPEN, OrderStatus.PENDING):
            self.pending_orders[response.order_id] = response
        self.orders.append(response)
        return response

    def cancel_order(self, order_id: str) -> OrderResponse:
        order = self.client.cancel_order(order_id)
        if order.status == OrderStatus.CANCELLED:
            self.pending_orders.pop(order_id, None)
        return order

    def process_market(self, timestamp: datetime, prices: Dict[str, float]) -> List[Fill]:
        """Evaluate pending LIMIT/STOP orders against current market prices."""
        fills: List[Fill] = []
        for order_id in list(self.pending_orders.keys()):
            order = self.pending_orders[order_id]
            price = prices.get(order.symbol)
            if price is None:
                continue
            fill = self._try_fill(order, price, timestamp)
            if fill:
                fills.append(fill)
                self.fills.append(fill)
                order.filled_quantity = order.quantity
                order.average_price = fill.price
                order.status = OrderStatus.COMPLETE
                self.pending_orders.pop(order_id)
        return fills

    def _try_fill(self, order: OrderResponse, price: float, timestamp: datetime) -> Optional[Fill]:
        if order.order_type == OrderType.MARKET:
            fill_price = price
        elif order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY and price <= (order.average_price or price):
                fill_price = order.average_price or price
            elif order.side == OrderSide.SELL and price >= (order.average_price or price):
                fill_price = order.average_price or price
            else:
                return None
        else:
            return None

        if order.side == OrderSide.BUY:
            fill_price, _, cost = self.cost_model.apply_buy(fill_price, order.quantity)
        else:
            fill_price, _, cost = self.cost_model.apply_sell(fill_price, order.quantity)

        self.portfolio.apply_fill(
            order.symbol,
            order.side.value,
            order.quantity,
            fill_price,
            cost.total,
        )
        return Fill(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            fees=cost.total,
            timestamp=timestamp,
        )

    def get_portfolio(self) -> PortfolioTracker:
        return self.portfolio

    def get_pnl(self, prices: Optional[Dict[str, float]] = None) -> PnL:
        if prices is None:
            symbols = [o.symbol for o in self.orders if o.status == OrderStatus.COMPLETE]
            prices = self._latest_prices(symbols)
        return self.portfolio.pnl(prices)

    def _latest_prices(self, symbols: List[str]) -> Dict[str, float]:
        prices: Dict[str, float] = {}
        for sym in set(symbols):
            try:
                df = self.data_provider.get_ohlcv(sym, "day")
                if df.height:
                    prices[sym] = float(df["Close"][-1])
            except Exception:
                logger.exception("Failed to fetch price for %s", sym)
        return prices

    def summary(self, prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        if prices is None:
            symbols = list(self.portfolio.positions.keys())
            prices = self._latest_prices(symbols)
        pnl = self.portfolio.pnl(prices)
        total_value = self.portfolio.total_value(prices)
        return {
            "cash": self.portfolio.cash,
            "total_value": total_value,
            "realized_pnl": pnl.realized,
            "unrealized_pnl": pnl.unrealized,
            "fees": pnl.fees,
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "average_cost": p.average_cost,
                    "market_value": p.market_value(prices.get(p.symbol, 0.0)),
                }
                for p in self.portfolio.positions.values()
            ],
        }
