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

## Phase 6

Cross-sectional pipeline and universe ranking in `quantmind/pipeline/`:

- `Pipeline` — declarative factor/filter container
- `Factor` / `Filter` — base classes with `rank`, `top`, `bottom`, `zscore`, `demean`, `winsorize`, and arithmetic operators
- `PipelineEngine` / `run_pipeline` — executes pipelines on long-form panels
- Built-in factors: `Returns`, `Latest`, `SMA`, `EMA`, `AverageDollarVolume`, `StaticPerSymbol`
- `PipelineMomentumStrategy` — bridge from pipeline rankings to `VectorBacktest` buy/sell signals
- `examples/pipeline_universe.py` — ranks a 10-asset synthetic universe by momentum and backtests the top-1 pick

```python
from quantmind.pipeline import Pipeline, run_pipeline
from quantmind.pipeline.factors.builtin import AverageDollarVolume, Latest, Returns

class MomentumPipeline(Pipeline):
    close = Latest("close")
    returns = Returns(window=5)
    universe = AverageDollarVolume(window=5).top(5)
    momentum_rank = returns.rank(mask=universe)

result = run_pipeline(panel, MomentumPipeline)
```

## Phase 6 acceptance

- Pipeline ranks a 10-symbol synthetic universe by momentum and the top pick is backtested via `VectorBacktest`.
- `rank`, `top`, `zscore`, `demean`, arithmetic, groups, and universe mask are tested.
- 67 unit tests pass.

## Phase 7

Storage and indexing layer in `quantmind/storage/`:

- `.iafbt` backtest bundles (`save_bundle` / `load_bundle`) — ZIP archives with JSON metadata and Parquet blobs
- `Tier1Store` — content-addressed Parquet store for OHLCV/factor DataFrames
- `SQLiteIndex` — index backtest runs and factor snapshots
- `RankIndex` — query top-N ranked symbols for a factor on a given date

```python
from quantmind.storage import save_bundle, load_bundle, SQLiteIndex, RankIndex

bundle_path = save_bundle("reliance_ma", result)
summary = load_bundle(bundle_path, summary_only=True)

index = SQLiteIndex()
index.insert_backtest(bundle_path, result, strategy_id="...", symbols=["RELIANCE"])
top = RankIndex(index).get_top(date(2024, 8, 6), "momentum", n=10)
```

## Phase 7 acceptance

- Backtest bundle round-trips (`BacktestResult` and `BacktestRun`) with summary-only loading.
- `Tier1Store` content-addressed storage for DataFrames.
- `RankIndex` stores and retrieves top-N factor snapshots.
- 73 unit tests pass.

## Phase 8

Agent backend in `quantmind/api/` and `quantmind/agent/`:

- FastAPI app with `/api/chat`, `/api/chat/stream` (SSE), `/api/approval/{request_id}`, `/health`
- `AgentSession` with `Tool` registry, `InMemoryMemory`, and approval gates
- `LLMClient` with `EchoLLM` (fallback/tests) and `OpenAILLM` (OpenAI-compatible)
- Built-in tools: `get_ohlcv`, `run_backtest`, `run_pipeline_rank`, `get_metrics`, `save_backtest_bundle`

Install API dependencies:

```bash
pip install -e '.[api]'
python examples/agent_server.py
```

```python
from fastapi.testclient import TestClient
from quantmind.api.main import app
client = TestClient(app)
resp = client.post("/api/chat", json={"message": "Run a backtest on RELIANCE"})
```

## Phase 8 acceptance

- `/api/chat` returns assistant and tool events.
- `/api/chat/stream` emits SSE events.
- Approval gates emit `approval_requested` and can be confirmed via `/api/approval/{request_id}`.
- 83 unit tests pass.
