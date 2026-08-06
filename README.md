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

## Phase 3

The vector backtest engine is in `quantmind/backtesting/`:

- `VectorBacktest` — multi-asset, Polars-first runner
- `BacktestResult`, `BacktestRun`, `Backtest` — result/configuration objects
- Supports `PositionSize`, `StopLossRule` (fixed/trailing), `TakeProfitRule` (fixed/trailing), `ScalingRule`, `CooldownRule`, `TradingCost`

```python
from examples.moving_average_crossover import MovingAverageCrossoverStrategy
from quantmind.backtesting import VectorBacktest
from quantmind.data.providers import UpstoxDataProvider
from quantmind.strategy import ParameterGrid, sweep

df = UpstoxDataProvider().get_ohlcv(
    "RELIANCE", "day", start="2019-08-06", end="2024-08-06"
)

def run(strategy):
    return VectorBacktest(strategy, {"RELIANCE_day": df}).run().total_return

grid = ParameterGrid({
    "fast_period": range(5, 30, 3),
    "slow_period": range(35, 95, 5),
})
result = sweep(MovingAverageCrossoverStrategy, grid, lambda s: {"total_return": run(s)})
print(result.best)
```

## Phase 3 acceptance

- 100 MA-window variants on RELIANCE daily data run in under 10 seconds.
- Multi-asset and single-asset backtests produce equity curves and trade lists.
- 42 unit tests pass, including deterministic accuracy checks against hand-calculated P&L, costs, stop-loss, take-profit, and trailing-stop exits, plus a `VectorBacktest` vs `SimpleBacktest` cross-check.

## Phase 4

The metrics and reporting layer is in `quantmind/metrics/` and `quantmind/reporting/`:

- 30+ metrics: total return, CAGR, Sharpe, Sortino, Calmar, max drawdown, drawdown duration, win rate, profit factor, trade expectancy, VaR, CVaR, skewness, kurtosis, exposure, beta/alpha/information/Treynor (with benchmark), monthly returns heatmap, and more.
- `BacktestReport` — generates JSON, Markdown, and HTML reports with equity curves, drawdown charts, and trade tables.

```python
from examples.generate_report import main

main()
# /tmp/reliance_ma_crossover_report.html
# /tmp/reliance_ma_crossover_report.json
```

## Phase 4 acceptance

- `BacktestReport` renders a full HTML/Markdown/JSON report for the MA-crossover backtest.
- 30+ metrics computed, including closed-form verified CAGR, drawdown, and profit factor.
- 54 unit tests pass.

## Phase 5

The event-driven backtest engine is in `quantmind/backtesting/`:

- `EventDrivenBacktest` — bar-by-bar runner with `ExecutionEngine`/`Blotter` and `Portfolio` tracking
- `Order`, `OrderSide`, `OrderType`, `OrderStatus` in `quantmind/domain/order.py`
- `IndianEquityCostModel` with brokerage, STT, stamp duty, transaction charges, SEBI charges, GST, and slippage
- Supports `MARKET`, `LIMIT`, `STOP`, and `STOP_LIMIT` orders with one-bar market-fill delay

```python
from quantmind.backtesting import EventDrivenBacktest, IndianEquityCostModel

cost_model = IndianEquityCostModel(brokerage_flat=20.0, slippage_pct=0.05)
result = EventDrivenBacktest(strategy, {"RELIANCE_day": df}, cost_model=cost_model).run()
```

## Phase 5 acceptance

- `EventDrivenBacktest` runs the MA-crossover strategy with realistic Indian CNC costs.
- `ExecutionEngine` fills market, limit, and stop orders correctly in unit tests.
- 59 unit tests pass.
