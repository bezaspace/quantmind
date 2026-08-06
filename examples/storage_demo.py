"""Demonstrate backtest bundle storage, indexing, and rank lookups."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl

from quantmind.backtesting import VectorBacktest
from quantmind.storage import RankIndex, SQLiteIndex, Tier1Store, load_bundle, save_bundle
from quantmind.storage.tier1 import Tier1Store
from examples.moving_average_crossover import MovingAverageCrossoverStrategy
from quantmind.data.providers import UpstoxDataProvider


def main():
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        index = SQLiteIndex(tmp_path / "index.sqlite")
        store = Tier1Store(tmp_path / "tier1")

        df = UpstoxDataProvider().get_ohlcv(
            "RELIANCE", "day", start="2019-08-06", end="2024-08-06"
        )
        # Store the OHLCV panel in Tier-1
        panel_digest = store.put(df, kind="ohlcv", key="RELIANCE_day_2019-2024")
        print("Tier1 OHLCV digest:", panel_digest)

        strategy = MovingAverageCrossoverStrategy(symbol="RELIANCE", fast_period=20, slow_period=50)
        result = VectorBacktest(
            strategy, {"RELIANCE_day": df}, initial_capital=1_000_000
        ).run()

        bundle_path = save_bundle(
            tmp_path / "reliance_ma",
            result,
            extra_metadata={"strategy": strategy.strategy_id},
        )
        print("Bundle saved:", bundle_path)

        index.insert_backtest(
            bundle_path,
            result,
            strategy_id=strategy.strategy_id,
            symbols=["RELIANCE"],
            backtest_id="demo-1",
            name="MA crossover RELIANCE",
        )

        # Rank index demo: synthetic factor snapshot
        snapshot = pl.DataFrame(
            {
                "symbol": ["RELIANCE", "TCS", "INFY", "HDFCBANK"],
                "value": [0.12, 0.08, 0.15, 0.05],
            }
        )
        index.insert_factor_snapshot(date(2024, 8, 6), "momentum", snapshot)

        rank_index = RankIndex(index)
        top = rank_index.get_top(date(2024, 8, 6), "momentum", n=3)
        print("Top momentum symbols:")
        print(top)

        # Load bundle summary without reading Parquet blobs
        summary = load_bundle(bundle_path, summary_only=True)
        print("Bundle summary total_return:", summary.metadata["total_return"])

        # Load full bundle
        loaded = load_bundle(bundle_path)
        print("Loaded trades:", loaded.trades.height)


if __name__ == "__main__":
    main()
