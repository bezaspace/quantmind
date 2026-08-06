# QuantMind India

AI-powered quant trading platform for the Indian equity market. Built from scratch with a chat-first interface.

## Phase 1

The market-data layer is implemented in `quantmind/data/`:

- `DataProvider` abstract base class
- `UpstoxDataProvider` — NSE/BSE OHLCV with 1m/30m/day/week/month support
- `YahooFinanceDataProvider` — daily/weekly/monthly fallback
- `OHLCVCache` — content-addressed Parquet + SQLite index
- `TradingCalendar` — NSE trading holidays

## Quick start

```bash
pip install -e ".[dev]"
export UPSTOX_ANALYTICS_TOKEN="your-token"  # or pass to UpstoxDataProvider
pytest
```

## Usage

```python
from quantmind.data.providers import UpstoxDataProvider

provider = UpstoxDataProvider()
df = provider.get_ohlcv(
    "RELIANCE", "day", start="2019-08-06", end="2024-08-06"
)
print(len(df))  # 1240 trading days
```

The `ChainedDataProvider` tries Upstox first and falls back to Yahoo Finance:

```python
from quantmind.data.providers import (
    ChainedDataProvider, UpstoxDataProvider, YahooFinanceDataProvider
)

chain = ChainedDataProvider([
    UpstoxDataProvider(),
    YahooFinanceDataProvider(),
])
```

## Phase 2

The strategy layer is implemented in `quantmind/domain/` and `quantmind/backtesting/`:

- `TradingStrategy` ABC — parameters, data sources, signal generation
- `quantmind/indicators/` — pure-Polars SMA, EMA, RSI, MACD, Bollinger, ATR, returns, volatility, crossover/crossunder
- `PositionSize`, `StopLossRule`, `TakeProfitRule`, `ScalingRule`, `CooldownRule`, `CooldownTracker`, `TradingCost`
- `ParameterGrid` + `sweep` for parameter search
- `SimpleBacktest` — single-asset bar-by-bar backtest runner
- `examples/moving_average_crossover.py` — example EMA crossover strategy

```python
from examples.moving_average_crossover import MovingAverageCrossoverStrategy
from quantmind.backtesting import SimpleBacktest
from quantmind.data.providers import UpstoxDataProvider

df = UpstoxDataProvider().get_ohlcv(
    "RELIANCE", "day", start="2019-08-06", end="2024-08-06"
)
strategy = MovingAverageCrossoverStrategy(symbol="RELIANCE", fast_period=20, slow_period=50)
result = SimpleBacktest(strategy, {"RELIANCE_day": df}, initial_capital=1_000_000).run()
print(result.total_return, result.num_trades, result.max_drawdown)
```

## Phase 2 acceptance

- A MA-crossover strategy can be defined and backtested on 5 years of RELIANCE daily data.
- Parameter sweep over fast/slow periods runs and finds the best combination.
- 31 unit tests pass.
