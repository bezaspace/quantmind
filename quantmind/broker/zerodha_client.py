"""Zerodha Kite Connect broker client (stub with paper support)."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx

from .base import BrokerClient
from .order import OrderRequest, OrderResponse, OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)


class ZerodhaBrokerClient(BrokerClient):
    """Zerodha Kite Connect broker client.

    Real trading requires a Kite Connect API key + access token. When those are
    not configured the client runs in paper mode and simulates fills.
    """

    BASE_URL = "https://api.kite.trade"

    def __init__(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        paper: Optional[bool] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("ZERODHA_API_KEY")
        self.access_token = access_token or os.getenv("ZERODHA_ACCESS_TOKEN")
        if paper is None:
            paper = not bool(self.access_token)
        self.paper = paper

        self.client = httpx.Client(timeout=30.0)
        if not self.paper and self.access_token:
            self.client.headers["Authorization"] = f"token {self.api_key}:{self.access_token}"
            self.client.headers["X-Kite-Version"] = "3"

        self._paper_orders: Dict[str, OrderResponse] = {}

    def place_order(self, request: OrderRequest) -> OrderResponse:
        if self.paper:
            return self._paper_place(request)

        # Kite order payload uses `tradingsymbol` and `exchange`
        body = {
            "tradingsymbol": request.symbol,
            "exchange": request.exchange,
            "transaction_type": request.side.value,
            "order_type": request.order_type.value,
            "quantity": str(int(request.quantity)),
            "product": request.product,
            "validity": request.validity,
        }
        if request.price is not None:
            body["price"] = str(request.price)
        if request.stop_price is not None:
            body["trigger_price"] = str(request.stop_price)

        resp = self.client.post(f"{self.BASE_URL}/orders/regular", data=body)
        resp.raise_for_status()
        data = resp.json()
        return OrderResponse(
            order_id=data.get("data", {}).get("order_id", str(uuid.uuid4())),
            status=OrderStatus.PENDING,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            message=data.get("data", {}).get("message"),
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        if self.paper:
            order = self._paper_orders.get(order_id)
            if order:
                order.status = OrderStatus.CANCELLED
            return order or self._unknown_order(order_id)
        resp = self.client.delete(f"{self.BASE_URL}/orders/regular/{order_id}")
        resp.raise_for_status()
        return OrderResponse(
            order_id=order_id,
            status=OrderStatus.CANCELLED,
            symbol="",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0,
        )

    def get_order_history(self, order_id: Optional[str] = None) -> List[OrderResponse]:
        if self.paper:
            orders = list(self._paper_orders.values())
            if order_id:
                return [o for o in orders if o.order_id == order_id]
            return orders

        url = f"{self.BASE_URL}/orders"
        resp = self.client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return [
            OrderResponse(
                order_id=o.get("order_id"),
                status=OrderStatus(o.get("status", "PENDING")),
                symbol=o.get("tradingsymbol", ""),
                side=OrderSide(o.get("transaction_type", "BUY")),
                order_type=OrderType(o.get("order_type", "MARKET")),
                quantity=float(o.get("quantity", 0)),
                filled_quantity=float(o.get("filled_quantity", 0)),
                average_price=o.get("average_price"),
            )
            for o in data.get("data", [])
        ]

    def get_positions(self) -> List[Dict[str, Any]]:
        if self.paper:
            return []
        resp = self.client.get(f"{self.BASE_URL}/portfolio/positions")
        resp.raise_for_status()
        return resp.json().get("data", {}).get("net", [])

    def get_funds(self) -> Dict[str, Any]:
        if self.paper:
            return {"paper": True, "cash": 0.0}
        resp = self.client.get(f"{self.BASE_URL}/user/margins")
        resp.raise_for_status()
        return resp.json().get("data", {})

    def _paper_place(self, request: OrderRequest) -> OrderResponse:
        order_id = f"zer-{uuid.uuid4().hex[:8]}"
        order = OrderResponse(
            order_id=order_id,
            status=OrderStatus.OPEN,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            average_price=request.price,
        )
        self._paper_orders[order_id] = order
        logger.info("Paper Zerodha order placed: %s", order_id)
        return order

    def _unknown_order(self, order_id: str) -> OrderResponse:
        return OrderResponse(
            order_id=order_id,
            status=OrderStatus.REJECTED,
            symbol="",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=0,
            message="Unknown order",
        )
