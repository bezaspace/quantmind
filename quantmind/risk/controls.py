"""Production risk controls for order execution and agent actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class RiskCheckResult:
    allowed: bool
    reasons: List[str]


class RiskController:
    """Validate orders and agent actions against configured limits."""

    def __init__(
        self,
        max_order_quantity: float = 10_000.0,
        max_daily_loss_pct: float = 5.0,
        allowed_products: List[str] | None = None,
        long_only: bool = True,
    ) -> None:
        self.max_order_quantity = max_order_quantity
        self.max_daily_loss_pct = max_daily_loss_pct
        self.allowed_products = {p.upper() for p in (allowed_products or ["CNC"])}
        self.long_only = long_only

    def check_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        product: str,
        price: float = 0.0,
        current_position: float = 0.0,
    ) -> RiskCheckResult:
        reasons: List[str] = []
        allowed = True

        if quantity <= 0:
            reasons.append("Quantity must be positive")
            allowed = False

        if quantity > self.max_order_quantity:
            reasons.append(f"Quantity {quantity} exceeds max {self.max_order_quantity}")
            allowed = False

        if product.upper() not in self.allowed_products:
            reasons.append(f"Product {product} not in allowed list {self.allowed_products}")
            allowed = False

        if self.long_only and side.upper() == "SELL" and quantity > current_position:
            reasons.append("Long-only: cannot sell more than current position")
            allowed = False

        return RiskCheckResult(allowed=allowed, reasons=reasons)

    def check_daily_loss(self, starting_equity: float, current_equity: float) -> RiskCheckResult:
        if starting_equity <= 0:
            return RiskCheckResult(allowed=True, reasons=[])
        loss_pct = (starting_equity - current_equity) / starting_equity * 100
        if loss_pct > self.max_daily_loss_pct:
            return RiskCheckResult(
                allowed=False,
                reasons=[
                    f"Daily loss {loss_pct:.2f}% exceeds limit {self.max_daily_loss_pct}%"
                ],
            )
        return RiskCheckResult(allowed=True, reasons=[])
