from datetime import datetime, timedelta

import polars as pl
import pytest

from quantmind.backtesting import EventDrivenBacktest
from quantmind.backtesting.blotter import ExecutionEngine, Portfolio
from quantmind.backtesting.costs import IndianEquityCostModel
from quantmind.domain import DataSource, Interval, PositionSize, TradingStrategy
from quantmind.domain.models import TimeUnit
from quantmind.domain.order import Order, OrderSide, OrderType


def _df(dates, close, symbol="RELIANCE"):
    return pl.DataFrame(
        {
            "Datetime": dates,
            "Open": close,
            "High": [c + 1 for c in close],
            "Low": [c - 1 for c in close],
            "Close": close,
            "Volume": [1000] * len(close),
        }
    )


class StaticSignalStrategy(TradingStrategy):
    time_unit = TimeUnit.DAY
    interval = 1

    def __init__(self, symbol: str, buy_bars: set, sell_bars: set):
        super().__init__(
            symbols=[symbol],
            data_sources=[DataSource(symbol=symbol, interval=Interval.DAY)],
            position_sizes=[PositionSize(symbol=symbol, percentage_of_portfolio=100)],
        )
        self.symbol = symbol
        self.buy_bars = set(buy_bars)
        self.sell_bars = set(sell_bars)

    def _make_signals(self, data):
        key = next(iter(data))
        n = len(data[key])
        return pl.Series("signal", [i in self.buy_bars for i in range(n)])

    def prepare_data(self, data):
        return data

    def generate_buy_signals(self, data):
        key = next(iter(data))
        n = len(data[key])
        return {self.symbol: pl.Series("buy", [i in self.buy_bars for i in range(n)])}

    def generate_sell_signals(self, data):
        key = next(iter(data))
        n = len(data[key])
        return {self.symbol: pl.Series("sell", [i in self.sell_bars for i in range(n)])}


def test_event_driven_buy_sell_market_order():
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(5)]
    close = [100.0, 100.0, 100.0, 110.0, 110.0]
    # buy at bar 0, sell at bar 2 -> fill buy at bar1 open 100, sell at bar3 open 110
    strategy = StaticSignalStrategy("RELIANCE", buy_bars={0}, sell_bars={2})
    df = _df(dates, close)
    result = EventDrivenBacktest(strategy, {"RELIANCE": df}, initial_capital=10_000).run()
    assert result.num_trades == 1
    assert result.total_return > 0


def test_execution_engine_limit_fill():
    model = IndianEquityCostModel(slippage_pct=0.0)
    engine = ExecutionEngine(cost_model=model)
    order = Order(
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=99.0,
    )
    engine.submit(order)
    bar = {"Open": 100.0, "High": 101.0, "Low": 98.0, "Close": 100.0, "Volume": 1000}
    fills = engine.process_bar(datetime(2023, 1, 1), {"RELIANCE": bar})
    assert len(fills) == 1
    assert fills[0].fill_price == 99.0


def test_execution_engine_stop_sell_fill():
    model = IndianEquityCostModel(slippage_pct=0.0)
    engine = ExecutionEngine(cost_model=model)
    order = Order(
        symbol="RELIANCE",
        side=OrderSide.SELL,
        order_type=OrderType.STOP,
        quantity=10,
        stop_price=95.0,
    )
    engine.submit(order)
    bar = {"Open": 100.0, "High": 100.0, "Low": 94.0, "Close": 96.0, "Volume": 1000}
    fills = engine.process_bar(datetime(2023, 1, 1), {"RELIANCE": bar})
    assert len(fills) == 1
    assert fills[0].fill_price == 95.0


def test_indian_cost_model_buy_sell():
    model = IndianEquityCostModel(
        brokerage_flat=20.0,
        stt_pct_sell=0.1,
        stamp_duty_pct_buy=0.015,
        transaction_charge_pct=0.00325,
        gst_pct=18.0,
        sebi_per_crore=10.0,
        slippage_pct=0.0,
    )
    fill_price, total_outflow, cost = model.apply_buy(100.0, 100)
    assert fill_price == 100.0
    assert cost.total > 0
    assert cost.stamp_duty > 0
    assert cost.stt == 0.0  # no STT on buy

    fill_price, total_inflow, cost = model.apply_sell(110.0, 100)
    assert cost.stt > 0
    assert total_inflow < fill_price * 100


def test_event_driven_long_only_no_short_selling():
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(4)]
    close = [100.0, 110.0, 90.0, 80.0]
    # sell signal without position should be ignored
    strategy = StaticSignalStrategy("RELIANCE", buy_bars=set(), sell_bars={1, 2})
    df = _df(dates, close)
    result = EventDrivenBacktest(strategy, {"RELIANCE": df}, initial_capital=10_000).run()
    assert result.num_trades == 0
    assert result.total_return == 0.0
