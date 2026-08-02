# QuantMind India — Product Roadmap & Build Plan

> Indian stock market only · Technical analysis only · Chat-first · Built from scratch · No external quant-library dependency

---

## 1. The new ideology

QuantMind India is not a wrapper around an existing quant library. It is a **from-scratch implementation** of the same quant workflow that the `investing-algorithm-framework` demonstrates, applied specifically to the Indian equity market.

The `investing-algorithm-framework` repository is used **only as a reference** — to study how a professional-grade quant engine is structured, how a `TradingStrategy` abstraction works, how vector and event-driven backtest engines calculate results, how metrics are derived, how a storage/index layer scales, and how paper/live order execution is wired. We will re-implement every piece ourselves, in our own codebase, with our own data and execution adapters for the Indian market.

The product experience stays **chat-first**: a non-technical user describes a strategy in plain English, the AI agent turns it into a strategy spec, the quant engine backtests it, ranks variants, and can eventually run it on a paper account. All of this happens without the user ever seeing code, notebooks, or a CLI.

---

## 2. Product vision

A single-sentence promise:

> Describe an Indian-stock technical strategy in English, backtest it across years of NSE/BSE data, compare the winners, and safely run the best one on paper — all inside a chat.

### Scope boundaries for v1 and the near term

| In scope | Out of scope for v1 |
|----------|---------------------|
| NSE/BSE cash equities (CNC / delivery) | Crypto, forex, commodities |
| Technical analysis only | Fundamental analysis, news, sentiment |
| Daily / weekly / monthly strategies | Intraday, HFT, options, futures |
| Backtesting + paper trading simulation | Fully automated live execution |
| One broker integration first (Upstox, Yahoo Finance fallback) | Multi-broker smart order routing |
| Long-only swing/positional strategies | Short selling, leverage |

---

## 3. Reference material — how we use it

- Original reference: `https://github.com/coding-kitties/investing-algorithm-framework`
- Org fork for study: `https://github.com/bezaspace/investing-algorithm-framework`
- Existing project docs in this repo: `PROJECT_PLAN.md`, `PROGRESS.md`, `README.md`

We will **not** install `investing-algorithm-framework` as a dependency. We will read the source code in `investing_algorithm_framework/domain/`, `investing_algorithm_framework/services/`, `investing_algorithm_framework/infrastructure/`, and `investing_algorithm_framework/app/` to understand the architecture, then write equivalent modules in our own codebase. The public API shape of the reference library is a useful design target because it is proven and easy to explain in interviews, but every line of code in QuantMind India will be original.

---

## 4. Data providers for the Indian market

### Primary: Upstox API

- **Historical candles:** `1minute` (last month), `30minute` (last year), `day` / `week` / `month` (up to 10 years).
- **Instrument master:** Daily BOD file maps symbols to exchange instrument tokens.
- **Live market feed:** WebSocket and quote APIs.
- **Order APIs:** Place / modify / cancel orders.
- **Sandbox:** A dedicated test environment for paper order integration.
- **Cost:** Free to use.
- **Requirement:** Upstox account, app, and access token.

### Fallback: Yahoo Finance

- Uses `yfinance` with `.NS` and `.BO` suffixes.
- Free, no account required.
- Best for daily historical backtests and quick prototyping.
- Data can be delayed or missing for some symbols.

### Future alternates

- **FYERS API:** Free historical data from 2017, intraday support.
- **Angel One SmartAPI:** Free historical and live data, order APIs.
- These will plug into the same `DataProvider` abstraction later.

### What the data layer must handle

1. **Instrument master sync:** Map `RELIANCE` → `NSE_EQ|INE002A01018` and cache it.
2. **Symbol normalization:** NSE vs BSE, indices vs stocks.
3. **Timeframe mapping:** Upstox intervals (`day`, `1minute`, `30minute`, etc.) and Yahoo intervals.
4. **Caching:** Never download the same OHLCV slice twice; use content-addressed storage.
5. **Holidays:** Skip NSE/BSE non-trading days in the backtest calendar.
6. **Adjusted prices:** Use provider-adjusted closes for splits, bonuses, and dividends in v1.

---

## 5. Indian market specifics the engine must model

### Market structure

- **Trading hours:** 09:15–15:30 IST.
- **Holidays:** Use an NSE/BSE holiday calendar.
- **Product type:** `CNC` (delivery) is the default for v1.
- **Order validity:** `DAY` is the default for v1.
- **Order types:** `MARKET` and `LIMIT` first; `SL` in a later phase.
- **Lot/tick size:** 1 share per lot for equities.
- **Position direction:** Long-only for CNC. Sell signals close existing long positions.

### Cost model

A realistic Indian brokerage and statutory cost model will be built incrementally:

- Phase 1: Simple percentage/flat commission per trade.
- Phase 2: Add STT (sell side, 0.1% for delivery), exchange charges, SEBI fee, GST, and stamp duty.
- The `TradingCost` / `CommissionModel` abstraction from the reference will be re-implemented so these can be swapped.

### Corporate actions

- v1 assumes the data provider returns adjusted OHLCV.
- Later phases will explicitly model dividends, splits, and bonuses in P&L and in the data pipeline.

### Compliance note

- Fully automated algo trading for retail investors is regulated by SEBI and exchanges. The rules require registration, static IP mapping, and broker controls.
- For v1, **live execution is not offered as an autonomous feature**. Any order placement requires explicit per-action user approval and is routed through the user’s own broker.
- All output must carry disclaimers: “Not investment advice,” “Past performance does not guarantee future results.”

---

## 6. Complete user flow

### 6.1 Onboarding

1. User signs up.
2. User connects an Upstox account in **sandbox** mode.
3. Assistant asks:
   - Risk tolerance.
   - Initial virtual capital (e.g., ₹10,00,000).
   - Universe (Nifty 50, Nifty 200, BSE 500, custom list).
   - Default timeframe (daily / weekly).

### 6.2 Build a strategy in chat

Example prompt:

> “Every Friday, buy the 10 Nifty 200 stocks with the highest 20-day return and hold them for one week. Use a 7% trailing stop.”

The agent returns a clean summary card:

- Universe: Nifty 200
- Lookback: 20 days
- Top N: 10
- Rebalance: Weekly Friday
- Trailing stop: 7%
- Product: CNC

### 6.3 Fast vector backtest

The agent runs the strategy across a date range (e.g., 2019–2024) and optionally sweeps:

- Lookback: 10, 20, 30 days.
- Top N: 5, 10, 20.
- Trailing stop: 5%, 7%, 10%.

Results are ranked and shown in a table.

### 6.4 Inspect a winner

User says:

> “Show me the best one.”

The assistant returns:

- Equity curve vs Nifty 50 benchmark.
- Drawdown chart.
- Monthly returns heatmap.
- Trade list.
- Key metrics: CAGR, Sharpe, Sortino, Calmar, max drawdown, win rate, profit factor.
- Monte Carlo p-value.

### 6.5 Validate with realistic execution

User says:

> “Re-run with 0.05% slippage and include brokerage.”

The event-driven engine re-simulates bar by bar with realistic fills and costs.

### 6.6 Compare and select

User compares top candidates side by side.

### 6.7 Approve paper trading

The assistant shows an approval card with broker, virtual capital, and risk controls. The user approves or edits.

### 6.8 Monitor and iterate

- “Show my open positions and today’s P&L.”
- “Why did it sell TCS today?”
- “Pause the bot.”
- “Change the trailing stop to 10%.”

Every mutating action goes through an approval gate.

---

## 7. Architecture

```
React + TypeScript Chat UI
         │
         │ SSE / REST
         ▼
Python FastAPI Agent Backend
         │
         ▼
QuantMind India Quant Engine (built from scratch)
  ├── Data Layer
  │     ├── UpstoxDataProvider (primary)
  │     ├── YahooFinanceDataProvider (fallback)
  │     ├── InstrumentMaster / SymbolResolver
  │     └── OHLCV cache and dedup store
  ├── Strategy Engine
  │     ├── TradingStrategy
  │     ├── PositionSize, StopLossRule, TakeProfitRule
  │     ├── ScalingRule, CooldownRule, TradingCost
  │     └── Indicator library (MA, RSI, MACD, Bollinger, ATR, momentum, volume)
  ├── Backtest Engines
  │     ├── VectorBacktest (fast sweeps)
  │     └── EventBacktest (bar-by-bar realism)
  ├── Metrics & Reporting
  │     ├── 30+ metrics
  │     ├── Equity / drawdown / heatmap charts
  │     └── BacktestReport (HTML + inline JSON)
  ├── Cross-Sectional Pipeline
  │     ├── Pipeline, Factor, CustomFactor, Filter
  │     └── Built-in factors (Returns, SMA, RSI, Volatility, AverageDollarVolume)
  ├── Storage & Index
  │     ├── Backtest bundles (.iafbt-style, zstd + msgpack + Parquet blobs)
  │     └── SQLite index for fast ranking
  └── Paper Trading
        ├── Upstox sandbox OrderExecutor
        ├── Portfolio / Position / Trade persistence
        └── Paper P&L tracking
```

---

## 8. Build phases

### Phase 0 — Repo setup and study

- Confirm scope.
- Study the reference `investing-algorithm-framework` source for the modules we will re-implement.
- Set up Python environment, FastAPI skeleton, and dependencies.
- Add Upstox SDK and `yfinance`.
- Configure secrets for Upstox and LLM provider.
- Create this `INDIA_ROADMAP.md` file.

### Phase 1 — Indian market data layer

- Implement a `DataProvider` abstract base class.
- Implement `UpstoxDataProvider`:
  - OAuth / access-token handling.
  - Instrument master download and cache.
  - Historical candle fetch.
  - Symbol → instrument token resolution.
- Implement `YahooFinanceDataProvider` as daily historical fallback.
- Implement local OHLCV cache and content-addressed dedup.
- Add NSE/BSE holiday calendar.
- **Acceptance:** Fetch and cache 5 years of RELIANCE daily data in under 2 seconds from cache.

### Phase 2 — Strategy abstraction

- Re-implement `TradingStrategy`:
  - `symbols`, `universe`, `time_unit`, `interval`.
  - `data_sources`.
  - `position_sizes`, `stop_losses`, `take_profits`.
  - `scaling_rules`, `cooldowns`, `trading_costs`.
  - `generate_buy_signals(data)` and `generate_sell_signals(data)`.
- Add Indian-market-aware defaults (CNC, long-only).
- Build an indicator helper library.
- Add parameter-sweep helper.
- **Acceptance:** A simple MA-crossover strategy can be defined and backtested.

### Phase 3 — Vector backtest engine

- Re-implement a Polars/pandas vectorized backtest engine.
- Apply position sizing, stop losses, take profits, trailing stops, cooldowns, and costs.
- Support single-asset and multi-asset strategies.
- Return a `Backtest` object with runs and per-run metrics.
- **Acceptance:** Run 100 MA-window variants on one stock in under 10 seconds.

### Phase 4 — Metrics and reporting

- Re-implement 30+ metrics: CAGR, Sharpe, Sortino, Calmar, max drawdown, win rate, profit factor, trade duration, exposure, etc.
- Build `BacktestReport` with equity curves, drawdowns, monthly heatmaps, trade tables, and metric cards.
- Produce both standalone HTML and inline JSON for the chat UI.
- **Acceptance:** Render a readable report for the MA-crossover backtest.

### Phase 5 — Event-driven backtest engine

- Re-implement a bar-by-bar simulator.
- Add `Blotter`, `SlippageModel`, `CommissionModel`, and `FillModel` abstractions.
- Model market, limit, and partial fills.
- Enforce stop losses, take profits, trailing stops, cooldowns, and scaling.
- Add an Indian cost model.
- **Acceptance:** Event-driven result for a simple strategy matches the vector result within a small tolerance.

### Phase 6 — Cross-sectional pipelines

- Re-implement `Pipeline`, `Factor`, `CustomFactor`, and `Filter`.
- Add built-in factors: `Returns`, `SMA`, `EMA`, `RSI`, `MACD`, `Volatility`, `AverageDollarVolume`.
- Support ranking a universe (Nifty 50, Nifty 200, custom list) every rebalance period.
- Build top-N rebalancing strategies.
- **Acceptance:** Run a “weekly top 10 momentum Nifty 200” strategy end-to-end.

### Phase 7 — Storage and index

- Design a `.iafbt`-style backtest bundle format (zstd + msgpack + Parquet metric blobs).
- Build a SQLite Tier-1 index with one row per backtest.
- Implement `BacktestStore` abstraction and `LocalDirStore`.
- Implement `rank_index()` for fast filtering/ranking.
- **Acceptance:** Index 1,000 backtests and rank by Sharpe in under 100 ms.

### Phase 8 — Agent backend

- Build the LLM tool catalog:
  - `create_strategy_from_description`
  - `run_vector_backtest`
  - `run_event_backtest`
  - `rank_strategies`
  - `generate_report`
  - `deploy_to_paper`
- Implement intent parsing into structured strategy specs.
- Add streaming SSE responses.
- Add human-in-the-loop approval gates.
- **Acceptance:** User can type a strategy description and get a backtest result in chat.

### Phase 9 — Chat UI

- Build React + TypeScript chat interface.
- Render text, charts (ECharts/Recharts), ranked tables, and approval cards.
- Add SSE streaming for long-running backtests.
- Add a strategy library and backtest gallery.
- **Acceptance:** The full chat-driven backtest flow works in the browser.

### Phase 10 — Paper trading with Upstox sandbox

- Re-implement an `OrderExecutor` ABC and `UpstoxOrderExecutor`.
- In-app paper portfolio and P&L tracking.
- Place, modify, and cancel sandbox orders.
- Reconcile positions and holdings.
- Daily activity report.
- **Acceptance:** A strategy can be deployed to sandbox and place paper orders.

### Phase 11 — Production hardening

- User accounts, authentication, encrypted API-key storage.
- Market-hours and holiday checks.
- Risk controls: max drawdown kill switch, daily loss limit, max position size, banned symbols.
- Alerts for approvals, errors, and large losses.
- Logging and audit trail.
- Disclaimers and risk disclosures.

### Phase 12 — Future expansion

- Intraday strategies and MIS product support.
- FYERS / Angel One SmartAPI adapters.
- Fundamental data sources for Indian stocks.
- Pairs trading and index overlays.
- Options/futures (last, after the core engine is proven).

---

## 9. MVP definition

The minimum lovable product is the combination of **Phase 0 through Phase 7** plus the start of **Phase 8**:

- A user can describe an Indian-stock technical strategy in chat.
- The agent generates a `TradingStrategy`.
- Vector backtests run with parameter sweeps.
- Results are ranked via the SQLite index.
- An inline report with equity curve, drawdown, and metrics is rendered.
- The user can iterate in chat.

Paper trading and the polished React UI come immediately after the engine is demoable.

---

## 10. What makes this interview-defensible

- **From-scratch quant engine:** We re-implement strategy abstractions, vector/event backtest engines, metrics, storage, and execution ourselves.
- **Domain specialization:** We adapt a generic quant framework to the Indian market — data providers, holidays, product types, cost model, and compliance.
- **Agent architecture:** The chat agent is the user interface; every quant operation is exposed as an LLM tool with approval gates.
- **System design:** Tiered storage, content-addressed dedup, and fast ranking show data-engineering depth.
- **Full-stack product:** React UI, FastAPI backend, Python quant engine, and broker integration form a complete portfolio piece.

---

## 11. Open questions before implementation

1. **Primary broker:** Upstox (recommended because of sandbox and existing Upstox credentials), or FYERS / Angel One?
2. **First timeframe:** Daily/weekly swing strategies only, or include intraday from the start?
3. **First universe:** Nifty 50, Nifty 200, BSE 500, or a custom watchlist?
4. **Cost model:** Simple percentage/flat fee for v1, or full Indian statutory-charge model from the start?
5. **Paper mode:** In-app simulation with EOD prices, or actual Upstox sandbox order placement?
6. **Fallback data:** Should Yahoo Finance be the first historical fallback, or FYERS/Angel One?

---

## 12. Conclusion

QuantMind India is a focused, from-scratch rebuild of a professional quant workflow for the Indian equity market. It keeps the chat-first experience of the original QuantMind idea but narrows scope to **NSE/BSE stocks**, **technical analysis**, and **paper trading first**. The `investing-algorithm-framework` is a study reference, not a dependency. The first concrete implementation step after this roadmap is approved is **Phase 1: build the Indian market data layer**.
