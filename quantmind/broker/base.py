"""Broker client abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .order import OrderRequest, OrderResponse


class BrokerClient(ABC):
    """Pluggable broker client for order placement and portfolio queries."""

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResponse: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse: ...

    @abstractmethod
    def get_order_history(self, order_id: Optional[str] = None) -> List[OrderResponse]: ...

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def get_funds(self) -> Dict[str, Any]: ...
