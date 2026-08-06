"""Run a Pipeline-ranked momentum strategy on a synthetic multi-asset universe."""

from datetime import datetime, timedelta

import polars as pl

from quantmind.backtesting import VectorBacktest
from quantmind.pipeline import Pipeline
from quantmind.pipeline.factors.builtin import AverageDollarVolume, Latest, Returns
from quantmind.pipeline.strategy_bridge import PipelineMomentumStrategy


def build_panel(n_symbols: int = 10, n_bars: int = 60):
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(n_bars)]
    data = {}
    for j in range(n_symbols):
        sym = f"SYM{j}"
        # Give later symbols stronger momentum so ranking is meaningful
        base = 100.0 + j * 10
        close = [base + i * (j + 1) * 0.5 for i in range(n_bars)]
        volume = [1000 * (j + 1)] * n_bars
        df = pl.DataFrame(
            {
                "Datetime": dates,
                "Open": [c - 1 for c in close],
                "High": [c + 1 for c in close],
                "Low": [c - 2 for c in close],
                "Close": close,
                "Volume": volume,
            }
        )
        data[sym] = df
    return data


def main():
    data = build_panel(n_symbols=10, n_bars=60)
    symbols = list(data.keys())

    class MomentumPipeline(Pipeline):
        close = Latest("close")
        returns = Returns(window=5)
        dollar_volume = AverageDollarVolume(window=5)
        universe = dollar_volume.top(5)
        momentum_rank = returns.rank(mask=universe)

    strategy = PipelineMomentumStrategy(
        symbols=symbols,
        pipeline=MomentumPipeline,
        top_n=1,
        rank_column="momentum_rank",
    )
    result = VectorBacktest(
        strategy,
        data,
        initial_capital=1_000_000,
    ).run()

    print("total_return:", result.total_return)
    print("num_trades:", result.num_trades)
    print("max_drawdown:", result.max_drawdown)
    print("trades:")
    print(result.trades.head(10))


if __name__ == "__main__":
    main()
