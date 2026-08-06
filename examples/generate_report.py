"""Generate a BacktestReport for the MA-crossover strategy."""

from examples.moving_average_crossover import MovingAverageCrossoverStrategy
from quantmind.backtesting import VectorBacktest
from quantmind.data.providers import UpstoxDataProvider
from quantmind.reporting import BacktestReport


def main():
    df = UpstoxDataProvider().get_ohlcv(
        "RELIANCE", "day", start="2019-08-06", end="2024-08-06"
    )
    strategy = MovingAverageCrossoverStrategy(symbol="RELIANCE", fast_period=20, slow_period=50)
    result = VectorBacktest(strategy, {"RELIANCE_day": df}, initial_capital=1_000_000).run()
    report = BacktestReport.from_result(result, name="reliance-ma-crossover")

    print(report.to_markdown())
    report.save_html("/tmp/reliance_ma_crossover_report.html")
    report.save_json("/tmp/reliance_ma_crossover_report.json")
    print("\nSaved HTML to /tmp/reliance_ma_crossover_report.html")
    print("Saved JSON to /tmp/reliance_ma_crossover_report.json")


if __name__ == "__main__":
    main()
