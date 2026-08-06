"""Run a simple paper trading session on RELIANCE."""

from quantmind.broker import (
    OrderRequest,
    OrderSide,
    OrderType,
    PaperTradingExecutor,
)
from quantmind.broker.upstox_client import UpstoxBrokerClient


def main():
    executor = PaperTradingExecutor(
        initial_capital=1_000_000.0,
        client=UpstoxBrokerClient(paper=True),
    )

    # Place a CNC market buy for RELIANCE
    req = OrderRequest(
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        product="CNC",
    )
    order = executor.place_order(req)
    print("Placed order:", order.order_id, order.status.value)

    # Simulate market open with latest price from data provider
    from datetime import datetime

    prices = executor._latest_prices(["RELIANCE"])
    if prices:
        executor.process_market(datetime.utcnow(), prices)

    summary = executor.summary(prices)
    print("Portfolio summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
