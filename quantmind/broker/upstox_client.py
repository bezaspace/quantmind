"""Upstox broker client with paper-trading fallback."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx

from .order import OrderRequest, OrderResponse, OrderStatus

logger = logging.getLogger(__name__)


class UpstoxBrokerClient:
    """Sync Upstox v2 broker client.

    When ``paper=True`` (or no access token is available), orders are simulated
    locally and assigned UUID order IDs.
    """

    BASE_URL = "https://api.upstox.com/v2"

    def __init__(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        paper: Optional[bool] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("UPSTOX_API_KEY")
        self.access_token = access_token or os.getenv("UPSTOX_ACCESS_TOKEN") or os.getenv("UPSTOX_ANALYTICS_TOKEN")
        if paper is None:
            paper = not bool(self.access_token)
        self.paper = paper

        self.client = httpx.Client(timeout=30.0)
        if not self.paper and self.access_token:
            self.client.headers["Authorization"] = f"Bearer {self.access_token}"
            self.client.headers["Api-Version"] = "2.0"
            self.client.headers["Content-Type"] = "application/json"

        self._paper_orders: Dict[str, OrderResponse] = {}
        self._paper_positions: Dict[str, Any] = {}

    def place_order(self, request: OrderRequest) -> OrderResponse:
        if self.paper:
            return self._paper_place(request)

        body = {
            "quantity": str(int(request.quantity)),
            "order_type": request.order_type.value,
            "transaction_type": request.side.value,
            "product": request.product,
            "exchange": request.exchange,
            "validity": request.validity,
        }
        if request.price is not None:
            body["price"] = str(request.price)
        if request.stop_price is not None:
            body["trigger_price"] = str(request.stop_price)

        # instrument_token is required; resolve if possible
        instrument_key = self._resolve_instrument_key(request.symbol, request.exchange)
        if instrument_key:
            body["instrument_token"] = instrument_key
        else:
            body["instrument_token"] = request.symbol

        resp = self.client.post(f"{self.BASE_URL}/order/place", json=body)
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
        resp = self.client.delete(f"{self.BASE_URL}/order/cancel?order_id={order_id}")
        resp.raise_for_status()
        data = resp.json()
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

        url = f"{self.BASE_URL}/order/history"
        if order_id:
            url += f"?order_id={order_id}"
        resp = self.client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return [
            OrderResponse(
                order_id=o.get("order_id"),
                status=OrderStatus(o.get("status", "PENDING")),
                symbol=o.get("symbol", ""),
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
            return list(self._paper_positions.values())
        resp = self.client.get(f"{self.BASE_URL}/portfolio/positions")
        resp.raise_for_status()
        return resp.json().get("data", [])

    def get_funds(self) -> Dict[str, Any]:
        if self.paper:
            return {"paper": True, "cash": 0.0}
        resp = self.client.get(f"{self.BASE_URL}/user/get-funds-and-margin")
        resp.raise_for_status()
        return resp.json().get("data", {})

    def _paper_place(self, request: OrderRequest) -> OrderResponse:
        order_id = f"paper-{uuid.uuid4().hex[:8]}"
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
        logger.info("Paper order placed: %s", order_id)
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

    def _resolve_instrument_key(self, symbol: str, exchange: str) -> Optional[str]:
        try:
            from ..data.providers import UpstoxDataProvider

            provider = UpstoxDataProvider()
            instrument = provider.resolve_instrument(symbol, exchange)
            return instrument.get("instrument_key")
        except Exception:
            return None
