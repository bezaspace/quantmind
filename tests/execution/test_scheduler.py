from datetime import datetime

import polars as pl

from quantmind.data.providers import DataProvider
from quantmind.domain.calendar import TradingCalendar
from quantmind.execution import IntradayScheduler, SchedulerConfig
from quantmind.broker import PaperTradingExecutor, UpstoxBrokerClient
from quantmind.risk import RiskController


class FakeDataProvider(DataProvider):
    name = "FAKE"
    supported_intervals = set()

    def get_ohlcv(self, symbol, interval, start=None, end=None, exchange="NSE"):
        return pl.DataFrame(
            {
                "Datetime": [datetime(2024, 8, 6, 9, 30), datetime(2024, 8, 6, 9, 31)],
                "Open": [2500.0, 2501.0],
                "High": [2502.0, 2502.0],
                "Low": [2499.0, 2500.0],
                "Close": [2501.0, 2502.0],
                "Volume": [1000, 2000],
            }
        )

    def resolve_instrument(self, symbol, exchange="NSE"):
        return {"symbol": symbol, "instrument_key": f"{exchange}|{symbol}"}


def test_scheduler_market_hours():
    cal = TradingCalendar()
    open_t, close_t = cal.market_hours(datetime(2024, 8, 6).date())
    assert open_t.hour == 9 and open_t.minute == 15
    assert close_t.hour == 15 and close_t.minute == 30


def test_scheduler_tick_with_signal():
    scheduler = IntradayScheduler(
        config=SchedulerConfig(symbols=["RELIANCE"]),
        executor=PaperTradingExecutor(
            client=UpstoxBrokerClient(paper=True),
            risk_controller=RiskController(allowed_products=["CNC", "MIS"]),
        ),
        signal_fn=lambda symbol, bar: "BUY",
        data_provider=FakeDataProvider(),
    )
    result = scheduler.run_tick("RELIANCE")
    assert result is not None
    assert result["signal"] == "BUY"
    assert result["order"].status.value == "COMPLETE"
