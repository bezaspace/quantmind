from datetime import datetime

import pytest

from quantmind.broker import (
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperTradingExecutor,
    PortfolioTracker,
    Position,
)
from quantmind.broker.upstox_client import UpstoxBrokerClient


def test_paper_order_lifecycle():
    client = UpstoxBrokerClient(paper=True)
    req = OrderRequest(
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
    )
    order = client.place_order(req)
    assert order.status == OrderStatus.OPEN
    assert order.order_id.startswith("paper-")

    history = client.get_order_history(order.order_id)
    assert len(history) == 1

    cancelled = client.cancel_order(order.order_id)
    assert cancelled.status == OrderStatus.CANCELLED


def test_portfolio_apply_fill():
    pf = PortfolioTracker(cash=100_000.0)
    pf.apply_fill("RELIANCE", "BUY", 10, 2500.0, 50.0)
    assert pf.cash == 100_000.0 - 10 * 2500.0 - 50.0
    assert pf.position("RELIANCE").quantity == 10

    realized = pf.apply_fill("RELIANCE", "SELL", 5, 2600.0, 25.0)
    assert realized == 5 * (2600.0 - 2500.0)
    assert pf.position("RELIANCE").quantity == 5


def test_position_unrealized_pnl():
    pos = Position(symbol="RELIANCE", quantity=10, average_cost=2500.0)
    assert pos.unrealized_pnl(2600.0) == pytest.approx(1000.0)


def test_paper_executor_market_fill():
    executor = PaperTradingExecutor(
        initial_capital=1_000_000.0,
        client=UpstoxBrokerClient(paper=True),
    )
    req = OrderRequest(
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
    )
    order = executor.place_order(req)
    prices = {"RELIANCE": 2500.0}
    fills = executor.process_market(datetime.utcnow(), prices)
    assert len(fills) == 1
    assert order.status == OrderStatus.COMPLETE
    assert executor.portfolio.position("RELIANCE").quantity == 10


def test_paper_executor_limit_fill():
    executor = PaperTradingExecutor(
        initial_capital=1_000_000.0,
        client=UpstoxBrokerClient(paper=True),
    )
    req = OrderRequest(
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=2500.0,
    )
    order = executor.place_order(req)
    # Market price at or below limit -> fill
    executor.process_market(datetime.utcnow(), {"RELIANCE": 2495.0})
    assert order.status == OrderStatus.COMPLETE


def test_paper_executor_sell_realized_pnl():
    executor = PaperTradingExecutor(
        initial_capital=1_000_000.0,
        client=UpstoxBrokerClient(paper=True),
    )
    executor.place_order(
        OrderRequest(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
    )
    executor.process_market(datetime.utcnow(), {"RELIANCE": 2500.0})
    executor.place_order(
        OrderRequest(
            symbol="RELIANCE",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=10,
        )
    )
    executor.process_market(datetime.utcnow(), {"RELIANCE": 2600.0})
    pnl = executor.get_pnl({"RELIANCE": 2600.0})
    assert pnl.realized > 0
