"""Run an event-driven MA-crossover backtest with Indian cost model."""

from examples.moving_average_crossover import MovingAverageCrossoverStrategy
from quantmind.backtesting import EventDrivenBacktest
from quantmind.backtesting.costs import IndianEquityCostModel
from quantmind.data.providers import UpstoxDataProvider


def main():
    df = UpstoxDataProvider().get_ohlcv(
        "RELIANCE", "day", start="2019-08-06", end="2024-08-06"
    )
    strategy = MovingAverageCrossoverStrategy(symbol="RELIANCE", fast_period=20, slow_period=50)
    cost_model = IndianEquityCostModel(
        brokerage_flat=20.0,
        stt_pct_sell=0.1,
        stamp_duty_pct_buy=0.015,
        transaction_charge_pct=0.00325,
        gst_pct=18.0,
        sebi_per_crore=10.0,
        slippage_pct=0.05,
    )
    result = EventDrivenBacktest(
        strategy,
        {"RELIANCE_day": df},
        initial_capital=1_000_000,
        cost_model=cost_model,
    ).run()
    print("total_return:", result.total_return)
    print("max_drawdown:", result.max_drawdown)
    print("num_trades:", result.num_trades)
    print("win_rate:", result.win_rate)
    print("first trade:", result.trades.head(1).to_dicts())


if __name__ == "__main__":
    main()
