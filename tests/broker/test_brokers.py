from quantmind.broker import (
    BrokerClient,
    OrderRequest,
    OrderSide,
    OrderType,
    UpstoxBrokerClient,
    ZerodhaBrokerClient,
)


def test_broker_client_is_abstract():
    assert BrokerClient.__abstractmethods__


def test_zerodha_paper_order():
    client = ZerodhaBrokerClient(paper=True)
    order = client.place_order(
        OrderRequest(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
    )
    assert order.order_id.startswith("zer-")
    assert order.status.value == "OPEN"


def test_upstox_paper_order():
    client = UpstoxBrokerClient(paper=True)
    order = client.place_order(
        OrderRequest(
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
    )
    assert order.order_id.startswith("paper-")
    assert order.status.value == "OPEN"
