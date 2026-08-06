"""Portfolio tracking and P&L computation for live/paper trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    average_cost: float = 0.0

    def market_value(self, price: float) -> float:
        return self.quantity * price

    def unrealized_pnl(self, price: float) -> float:
        if self.quantity == 0:
            return 0.0
        return self.quantity * (price - self.average_cost)

    def buy(self, quantity: float, price: float) -> None:
        total_cost = self.quantity * self.average_cost + quantity * price
        self.quantity += quantity
        if self.quantity > 0:
            self.average_cost = total_cost / self.quantity

    def sell(self, quantity: float, price: float) -> float:
        """Return realized PnL for the sold quantity."""
        if quantity > self.quantity:
            quantity = self.quantity
        realized = quantity * (price - self.average_cost)
        self.quantity -= quantity
        if self.quantity <= 0:
            self.average_cost = 0.0
        return realized


@dataclass
class PnL:
    realized: float = 0.0
    unrealized: float = 0.0
    fees: float = 0.0

    @property
    def total(self) -> float:
        return self.realized + self.unrealized - self.fees


@dataclass
class PortfolioTracker:
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    fees: float = 0.0

    def position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def apply_fill(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        fees: float = 0.0,
    ) -> float:
        pos = self.position(symbol)
        realized = 0.0
        if side == "BUY":
            total_outflow = quantity * price + fees
            self.cash -= total_outflow
            pos.buy(quantity, price)
        else:
            total_inflow = quantity * price - fees
            self.cash += total_inflow
            realized = pos.sell(quantity, price)
            self.realized_pnl += realized
        self.fees += fees
        return realized

    def total_value(self, prices: Dict[str, float]) -> float:
        total = self.cash
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, 0.0)
            total += pos.market_value(price)
        return total

    def pnl(self, prices: Dict[str, float]) -> PnL:
        unrealized = 0.0
        for symbol, pos in self.positions.items():
            price = prices.get(symbol, 0.0)
            if price:
                unrealized += pos.unrealized_pnl(price)
        return PnL(
            realized=self.realized_pnl,
            unrealized=unrealized,
            fees=self.fees,
        )
