# QuantMind India — Roadmap & Build Plan

> Indian stock market only · Technical analysis only · Chat-first · Built from scratch · No external quant-library dependency

---

## 1. Intention

QuantMind India is an **AI-powered quant trading platform** where the user operates a full
hedge-fund workflow through a single chat interface. The user never writes code, opens a
notebook, or touches a CLI — they describe a strategy in natural language and an AI agent
builds it, backtests it (vector + event-driven), ranks candidates across parameter sweeps,
generates reports, and deploys the winner to paper trading.

It is **not a wrapper** around an existing quant library. It is a **from-scratch
implementation** of the same quant workflow that the `investing-algorithm-framework`
demonstrates, applied specifically to the **Indian equity market**.

### What makes this interview-defensible

- **From-scratch quant engine:** We re-implement strategy abstractions, vector/event
  backtest engines, metrics, storage, and execution ourselves — every line of code is
  original and every architectural decision can be defended.
- **Domain specialization:** We adapt a generic quant framework to the Indian market —
  data providers, holidays, product types, cost model, and compliance.
- **Agent architecture:** The chat agent is the user interface; every quant operation is
  exposed as an LLM tool with approval gates.
- **System design:** Tiered storage, content-addressed dedup, and fast ranking show
  data-engineering depth.
- **Full-stack product:** React UI, FastAPI backend, Python quant engine, and broker
  integration form a complete portfolio piece.

These five distinct, hiring-relevant skill dimensions — AI agent architecture,
quantitative analysis, system design, data engineering, and full-stack engineering — are
each backed by code you can show and design decisions you can defend.

---

## 2. Product vision

A single-sentence promise:

> Describe an Indian-stock technical strategy in English, backtest it across years of
> NSE/BSE data, compare the winners, and safely run the best one on paper — all inside a
> chat.

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

## 3. Reference repository — how we use it

- **Original reference:** https://github.com/coding-kitties/investing-algorithm-framework
  (1.6k stars, Apache-2.0)
- **Org fork for parallel study:** https://github.com/bezaspace/investing-algorithm-framework
- **Reference framework docs:** https://coding-kitties.github.io/investing-algorithm-framework/

We will **not** install `investing-algorithm-framework` as a dependency. We will read the
source code in `investing_algorithm_framework/domain/`,
`investing_algorithm_framework/services/`,
`investing_algorithm_framework/infrastructure/`, and
`investing_algorithm_framework/app/` to understand the architecture, then write equivalent
modules in our own codebase. The public API shape of the reference library is a useful
design target because it is proven and easy to explain in interviews, but every line of
code in QuantMind India will be original.

The reference repository is the canonical source for the patterns we replicate:

| Reference repo component | QuantMind India module | What we study / re-implement |
|--------------------------|------------------------|------------------------------|
| `domain/strategy.py` | Strategy Engine | `TradingStrategy` abstraction, signal generation |
| `services/metrics/` | Metrics & Reporting | 30+ performance metrics |
| Vector backtesting module | VectorBacktest | Vectorized parameter sweeps |
| Event-driven backtesting module | EventBacktest | Bar-by-bar simulation, blotter |
| `domain/blotter.py` | EventBacktest | Simulation blotter, fill modeling |
| `services/backtest_index/` | Storage & Index | SQLite Tier-1 index |
| `services/backtest_store/` | Storage & Index | `BacktestStore` protocol |
| `infrastructure/database/` | Storage & Index | Content-addressed OHLCV dedup |
| `domain/pipeline/` | Cross-Sectional Pipeline | `Pipeline`, `Factor`, `Filter` |
| `domain/order_executor.py` | Paper Trading | `OrderExecutor` protocol |
| `infrastructure/order_executors/` | Paper Trading | Broker adapter pattern |
| `services/order_service/` | Paper Trading | Order management |
| `services/portfolios/` | Paper Trading | Portfolio persistence |
| `services/positions/` | Paper Trading | Position tracking |
| Permutation testing module | Metrics & Reporting | Monte Carlo robustness checks |
| BacktestReport module | Metrics & Reporting | HTML + inline report generation |

Keep the reference fork open in a browser tab while building. Cite which file/module you
studied in commit messages and PR descriptions.

---

## 4. Architecture

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

The same `TradingStrategy` abstraction runs unchanged in vector backtest, event-driven
backtest, and paper trading. Only the execution context changes. This is a core design
constraint — do not fork the strategy class per context.

---

## 5. Data providers for the Indian market

### Primary: Upstox API

- **Historical candles:** `1minute` (last month), `30minute` (last year), `day` / `week` /
  `month` (up to 10 years).
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
3. **Timeframe mapping:** Upstox intervals (`day`, `1minute`, `30minute`, etc.) and Yahoo
   intervals.
4. **Caching:** Never download the same OHLCV slice twice; use content-addressed storage.
5. **Holidays:** Skip NSE/BSE non-trading days in the backtest calendar.
6. **Adjusted prices:** Use provider-adjusted closes for splits, bonuses, and dividends in
   v1.

---

## 6. Indian market specifics the engine must model

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
- Phase 2: Add STT (sell side, 0.1% for delivery), exchange charges, SEBI fee, GST, and
  stamp duty.
- The `TradingCost` / `CommissionModel` abstraction from the reference will be
  re-implemented so these can be swapped.

### Corporate actions

- v1 assumes the data provider returns adjusted OHLCV.
- Later phases will explicitly model dividends, splits, and bonuses in P&L and in the data
  pipeline.

### Compliance note

- Fully automated algo trading for retail investors is regulated by SEBI and exchanges. The
  rules require registration, static IP mapping, and broker controls.
- For v1, **live execution is not offered as an autonomous feature**. Any order placement
  requires explicit per-action user approval and is routed through the user's own broker.
- All output must carry disclaimers: "Not investment advice," "Past performance does not
  guarantee future results."

---

## 7. Complete user flow

### 7.1 Onboarding

1. User signs up.
2. User connects an Upstox account in **sandbox** mode.
3. Assistant asks:
   - Risk tolerance.
   - Initial virtual capital (e.g., ₹10,00,000).
   - Universe (Nifty 50, Nifty 200, BSE 500, custom list).
   - Default timeframe (daily / weekly).

### 7.2 Build a strategy in chat

Example prompt:

> "Every Friday, buy the 10 Nifty 200 stocks with the highest 20-day return and hold them
> for one week. Use a 7% trailing stop."

The agent returns a clean summary card:

- Universe: Nifty 200
- Lookback: 20 days
- Top N: 10
- Rebalance: Weekly Friday
- Trailing stop: 7%
- Product: CNC

### 7.3 Fast vector backtest

The agent runs the strategy across a date range (e.g., 2019–2024) and optionally sweeps:

- Lookback: 10, 20, 30 days.
- Top N: 5, 10, 20.
- Trailing stop: 5%, 7%, 10%.

Results are ranked and shown in a table.

### 7.4 Inspect a winner

User says:

> "Show me the best one."

The assistant returns:

- Equity curve vs Nifty 50 benchmark.
- Drawdown chart.
- Monthly returns heatmap.
- Trade list.
- Key metrics: CAGR, Sharpe, Sortino, Calmar, max drawdown, win rate, profit factor.
- Monte Carlo p-value.

### 7.5 Validate with realistic execution

User says:

> "Re-run with 0.05% slippage and include brokerage."

The event-driven engine re-simulates bar by bar with realistic fills and costs.

### 7.6 Compare and select

User compares top candidates side by side.

### 7.7 Approve paper trading

The assistant shows an approval card with broker, virtual capital, and risk controls. The
user approves or edits.

### 7.8 Monitor and iterate

- "Show my open positions and today's P&L."
- "Why did it sell TCS today?"
- "Pause the bot."
- "Change the trailing stop to 10%."

Every mutating action goes through an approval gate.

---

## 8. Feature & skill mapping

Each feature below is re-implemented from scratch, studying the corresponding module in
the `investing-algorithm-framework` reference repository.

### 8.1 Strategy abstraction and market data
**What:** A `TradingStrategy` class with `symbols`, `universe`, `time_unit`, `interval`,
`position_sizes`, `stop_losses`, `take_profits`, `scaling_rules`, `cooldowns`,
`trading_costs`, and `generate_buy_signals` / `generate_sell_signals` methods. Indian-
market-aware defaults (CNC, long-only). A `DataProvider` ABC with `UpstoxDataProvider` and
`YahooFinanceDataProvider` implementations.

**Reference:** `investing_algorithm_framework/domain/strategy.py`, data provider modules.

**Job skill:** Domain modeling and adapter design. The strategy abstraction that runs
unchanged across backtest and live is a non-trivial design problem.

### 8.2 Vector backtesting engine
**What:** A Polars/pandas vectorized backtest engine supporting position sizing, stop
losses, take profits, trailing stops, cooldowns, and costs. Single-asset and multi-asset
strategies. Returns a `Backtest` object with runs and per-run metrics.

**Reference:** Vector backtesting module in the reference framework.

**Job skill:** Vectorized computation and parameter-sweep design. Running 100 variants in
seconds requires understanding vectorization and memory.

### 8.3 Event-driven backtesting engine
**What:** A bar-by-bar simulator with `Blotter`, `SlippageModel`, `CommissionModel`, and
`FillModel` abstractions. Models market, limit, and partial fills. Enforces stop losses,
take profits, trailing stops, cooldowns, and scaling. Includes the Indian cost model.

**Reference:** `investing_algorithm_framework/domain/blotter.py`, event-driven backtesting
module.

**Job skill:** Event-driven simulation is what separates toy backtests from
production-grade ones. Shows you understand execution realism, slippage modeling, and the
gap between backtest and live performance.

### 8.4 Backtest storage and indexing layer
**What:** A tiered storage architecture — Tier-1 SQLite index for sub-100ms ranking over
10k+ backtests, a swappable `BacktestStore` protocol, and content-addressed OHLCV
deduplication so market data is never fetched or stored twice. A `.iafbt`-style backtest
bundle format (zstd + msgpack + Parquet metric blobs).

**Reference:** `investing_algorithm_framework/services/backtest_index/`,
`services/backtest_store/`, `infrastructure/database/`.

**Job skill:** System design for high-volume research data. Content-addressed dedup and
tiered indexing are real production patterns. This is the "data engineering" signal.

### 8.5 Performance metrics (30+)
**What:** CAGR, Sharpe, Sortino, Calmar, VaR, CVaR, Max Drawdown, Recovery Factor, win
rate, profit factor, consistency score — computed correctly with edge-case handling
(division by zero, single-trade strategies, etc.).

**Reference:** `investing_algorithm_framework/services/metrics/`.

**Job skill:** Quantitative analysis. Computing these metrics *correctly* (not just
calling a library) is a quant-engineering competency. Interviewers will ask how you handle
annualization, downside deviation, and the corner cases.

### 8.6 Cross-sectional pipelines and factor tables
**What:** `Pipeline`, `Factor`, `CustomFactor`, and `Filter` classes. Built-in factors:
`Returns`, `SMA`, `EMA`, `RSI`, `MACD`, `Volatility`, `AverageDollarVolume`. Rank, filter,
and score entire universes (Nifty 50, Nifty 200, custom list) every rebalance period.

**Reference:** `investing_algorithm_framework/domain/pipeline/`.

**Job skill:** Cross-sectional analysis is a step up from single-asset backtesting. Shows
portfolio-level thinking and factor-model awareness.

### 8.7 Monte Carlo permutation testing
**What:** Statistical robustness checks across randomized market scenarios — shuffle trade
order, resample returns, and compute the distribution of outcomes to test whether a
strategy's edge is real or an artifact of sequence luck.

**Reference:** Permutation testing module in the reference framework.

**Job skill:** Statistical rigor. "I permutation-tested my strategy" is the difference
between a credible backtest and a curve-fit one.

### 8.8 BacktestReport generation
**What:** Self-contained HTML dashboard with equity curves, drawdowns, trade lists,
monthly returns, and strategy comparison. Also renderable as inline JSON/charts in the chat
for quick lookups.

**Reference:** BacktestReport module in the reference framework.

**Job skill:** Data visualization and reporting. A good report turns numbers into a
decision — shows you can communicate results, not just compute them.

### 8.9 Paper trading and deployment
**What:** An `OrderExecutor` ABC and `UpstoxOrderExecutor` for the Upstox sandbox.
In-app paper portfolio and P&L tracking. Place, modify, and cancel sandbox orders.
Reconcile positions and holdings. Daily activity report.

**Reference:** `investing_algorithm_framework/domain/order_executor.py`,
`infrastructure/order_executors/`, `services/order_service/`,
`services/portfolios/`, `services/positions/`.

**Job skill:** Production trading systems. Going from backtest to live is where most
strategies fail. Demonstrates execution-layer engineering, order management, and portfolio
state persistence.

### 8.10 AI chat agent (the interface)
**What:** An LLM agent with domain-specific tools (`create_strategy_from_description`,
`run_vector_backtest`, `run_event_backtest`, `rank_strategies`, `generate_report`,
`deploy_to_paper`), system-prompt engineering for quant workflows, streaming responses,
tool calling, and human-in-the-loop approval for any mutating/live action. The agent IS the
user interface — there is no other UI for the quant engine.

**Reference:** The reference framework exposes an MCP server so AI agents can query
backtests and rank strategies. QuantMind India goes further: the agent is the primary
interface, not an optional add-on.

**Job skill:** AI agent architecture — the core of the project. Tool calling, streaming,
intent-to-structured-spec parsing, and approval gates are exactly the patterns
interviewers for AI-engineering roles probe.

### 8.11 Chat UI (React + TypeScript)
**What:** A ChatGPT-style chat interface where the user types natural language and the
agent responds with text, inline charts (equity curves, drawdowns), ranked candidate
tables, approval cards, and deployment status. Streaming via SSE.

**Job skill:** Full-stack engineering. Building a real-time chat UI that renders rich
domain content (charts, tables, approval flows) — not just text — is the difference
between a demo and a product.

### 8.12 Two-stage cost optimization (optional/stretch)
**What:** A cheap model triages user intent and simple strategy specs; only complex spec
generation and result analysis hits the strong model. Target significant inference cost
reduction vs. naive single-model runs.

**Job skill:** Cost is the #1 blocker for agent products. Being able to quantify "this
design cut cost X%" is a standout resume line.

---

## 9. Build phases

### Phase 0 — Repo setup and study
- Confirm scope.
- Study the reference `investing-algorithm-framework` source for the modules we will
  re-implement.
- Set up Python environment, FastAPI skeleton, and dependencies.
- Add Upstox SDK and `yfinance`.
- Configure secrets for Upstox and LLM provider.
- Create this `ROADMAP.md` file.

### Phase 1 — Indian market data layer ✅
- [x] Implement a `DataProvider` abstract base class.
- [x] Implement `UpstoxDataProvider`:
  - [x] OAuth / access-token handling via `UPSTOX_ANALYTICS_TOKEN`.
  - [x] Instrument master download and cache.
  - [x] Historical candle fetch.
  - [x] Symbol → instrument token resolution.
  - [x] 1-minute and 30-minute interval support with automatic chunking.
- [x] Implement `YahooFinanceDataProvider` as daily/weekly/monthly historical fallback.
- [x] Implement `ChainedDataProvider` fallback from Upstox to Yahoo Finance.
- [x] Implement local OHLCV cache and content-addressed dedup.
- [x] Add NSE/BSE holiday calendar.
- [x] **Acceptance:** Fetch and cache 5 years of RELIANCE daily data in under 2 seconds from
  cache.

### Phase 2 — Strategy abstraction ✅
- [x] Re-implement `TradingStrategy`:
  - [x] `symbols`, `universe` (via `data_sources`), `time_unit`, `interval`.
  - [x] `data_sources`.
  - [x] `position_sizes`, `stop_losses`, `take_profits`.
  - [x] `scaling_rules`, `cooldowns`, `trading_costs`.
  - [x] `generate_buy_signals(data)` and `generate_sell_signals(data)`.
- [x] Add Indian-market-aware defaults (NSE, CNC, long-only).
- [x] Build an indicator helper library (`quantmind/indicators/` with pure Polars functions).
- [x] Add parameter-sweep helper (`quantmind/strategy/sweep.py`).
- [x] Add a lightweight single-asset `SimpleBacktest` runner to validate the abstraction.
- [x] **Acceptance:** A simple MA-crossover strategy can be defined and backtested on
  5 years of RELIANCE daily data.

### Phase 3 — Vector backtest engine ✅
- [x] Implement a Polars-first multi-asset backtest engine (`quantmind/backtesting/vector.py`).
- [x] Apply position sizing, stop losses, take profits, trailing stops, cooldowns, and costs.
- [x] Support single-asset and multi-asset strategies.
- [x] Return a `BacktestRun` result object (and `Backtest` configuration container).
- [x] **Acceptance:** Run 100 MA-window variants on one stock in under 10 seconds.

### Phase 4 — Metrics and reporting
- Re-implement 30+ metrics: CAGR, Sharpe, Sortino, Calmar, max drawdown, win rate, profit
  factor, trade duration, exposure, etc.
- Build `BacktestReport` with equity curves, drawdowns, monthly heatmaps, trade tables,
  and metric cards.
- Produce both standalone HTML and inline JSON for the chat UI.
- **Acceptance:** Render a readable report for the MA-crossover backtest.

### Phase 5 — Event-driven backtest engine
- Re-implement a bar-by-bar simulator.
- Add `Blotter`, `SlippageModel`, `CommissionModel`, and `FillModel` abstractions.
- Model market, limit, and partial fills.
- Enforce stop losses, take profits, trailing stops, cooldowns, and scaling.
- Add an Indian cost model.
- **Acceptance:** Event-driven result for a simple strategy matches the vector result
  within a small tolerance.

### Phase 6 — Cross-sectional pipelines
- Re-implement `Pipeline`, `Factor`, `CustomFactor`, and `Filter`.
- Add built-in factors: `Returns`, `SMA`, `EMA`, `RSI`, `MACD`, `Volatility`,
  `AverageDollarVolume`.
- Support ranking a universe (Nifty 50, Nifty 200, custom list) every rebalance period.
- Build top-N rebalancing strategies.
- **Acceptance:** Run a "weekly top 10 momentum Nifty 200" strategy end-to-end.

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
- Risk controls: max drawdown kill switch, daily loss limit, max position size, banned
  symbols.
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

## 10. MVP definition

The minimum lovable product is the combination of **Phase 0 through Phase 7** plus the
start of **Phase 8**:

- A user can describe an Indian-stock technical strategy in chat.
- The agent generates a `TradingStrategy`.
- Vector backtests run with parameter sweeps.
- Results are ranked via the SQLite index.
- An inline report with equity curve, drawdown, and metrics is rendered.
- The user can iterate in chat.

Paper trading and the polished React UI come immediately after the engine is demoable.

---

## 11. Build philosophy and guardrails

- **From scratch first.** Build the quant engine primitives yourself before building the
  chat agent on top. The reference repository is a *study reference*, not a dependency. Do
  not `pip install investing-algorithm-framework`. Read their code, understand the
  patterns, and write your own. This is the source of interview-defensible depth.
- **The reference repo is forked into our org for parallel study.** Use
  https://github.com/bezaspace/investing-algorithm-framework to read the canonical
  implementation of any component while building your own version. Keep it open in a
  browser tab. Cite which file/module you studied in commit messages and PR descriptions.
- **The agent is the interface.** There is no separate quant CLI or notebook UI for the
  user. Every quant operation is reachable through chat. The agent's tool layer wraps the
  quant engine; the user never calls the engine directly.
- **Same strategy class, three contexts.** The `TradingStrategy` abstraction runs
  unchanged in vector backtest, event-driven backtest, and paper trading. Only the
  execution context changes. This is a core design constraint — do not fork the strategy
  class per context.
- **Approval before mutation.** Any action that touches live trading, real money, or
  irreversible state requires a human approval gate. Read-only actions (backtest, rank,
  report) run without approval.
- **Demoable milestones.** Every milestone should produce something the user can see in the
  chat. Track cost, latency, and backtest accuracy from day one.
- **Markets: Indian equities first.** NSE/BSE cash equities via Upstox (primary) and Yahoo
  Finance (fallback). Crypto, forex, and commodities are out of scope for v1. This is a
  scoping decision, not a permanent limitation.
- **Live trading in v1: paper only.** v1 supports paper trading via the Upstox sandbox.
  Real money deployment is gated behind explicit configuration and a second approval
  layer. This is a safety guardrail, not a technical limitation.

---

## 12. What's decided vs. open

### Decided
- **The product:** an AI chat app for quant trading on the Indian equity market (not voice,
  not a library, not a CLI).
- **The approach:** build the quant engine from scratch using the
  `investing-algorithm-framework`'s architecture as reference (not importing it).
- **The interface:** chat-based, like ChatGPT — user types, agent does the rest.
- **The scope:** full quant workflow — strategy creation, backtesting (vector +
  event-driven), analysis, ranking, paper deployment.
- **First markets:** NSE/BSE cash equities (CNC / delivery).
- **Primary data provider:** Upstox API (with Yahoo Finance fallback).
- **Live trading in v1:** paper only via Upstox sandbox; real money deferred.
- **Strategy types:** technical analysis only, daily/weekly/monthly, long-only.
- **Reference repo:** forked to
  https://github.com/bezaspace/investing-algorithm-framework for parallel study.

### Open (to decide during the build)
- **Primary broker confirmation:** Upstox (recommended because of sandbox and existing
  credentials), or FYERS / Angel One?
- **First timeframe:** Daily/weekly swing strategies only, or include intraday from the
  start?
- **First universe:** Nifty 50, Nifty 200, BSE 500, or a custom watchlist?
- **Cost model:** Simple percentage/flat fee for v1, or full Indian statutory-charge model
  from the start?
- **Paper mode:** In-app simulation with EOD prices, or actual Upstox sandbox order
  placement?
- **Agent layer tech stack:** LangGraph? custom? which LLM provider? (LangGraph is the
  likely choice — model-agnostic, native tool calling, streaming, human-in-the-loop
  interrupts.)
- **Chat UI framework:** React + Vite vs. Next.js.
- **Charting library:** Recharts? ECharts? lightweight-charts?
- **How the agent presents backtest results:** inline charts (rendered client-side from
  JSON) vs. generated images vs. embedded HTML.

---

## 13. The interview story (one paragraph)

> "I built an AI-powered quant trading platform for the Indian equity market where the user
> operates a full hedge-fund workflow through a chat interface — no code, no notebooks. An
> LLM agent parses natural-language strategy descriptions, generates a typed strategy spec,
> runs vector backtests across thousands of parameter variants on years of NSE/BSE data,
> validates winners in event-driven simulation with slippage modeling and a realistic
> Indian brokerage cost model, ranks candidates across 30+ metrics (Sharpe, Sortino,
> Calmar, VaR, CVaR, Max DD), runs Monte Carlo permutation testing for statistical
> robustness, presents equity curves and drawdowns inline in the chat, and deploys the
> winner to paper trading via the Upstox sandbox — with human approval gates before any
> live action. The quant engine is built from scratch (strategy abstraction, vector +
> event-driven backtest engines, tiered SQLite storage with content-addressed OHLCV dedup,
> cross-sectional factor pipelines), inspired by but not importing the
> investing-algorithm-framework architecture."

That single paragraph demonstrates five distinct, hiring-relevant skill dimensions — AI
agent architecture, quantitative analysis, system design, data engineering, and full-stack
engineering — each backed by code you can show and design decisions you can defend.

---

## 14. Implementation progress

| Phase | Goal | Status | Notes |
|-------|------|--------|-------|
| 0 | Repo, roadmap, reference fork | Done | `ROADMAP.md` created, reference repo forked into org |
| 1 | Indian market data layer (Upstox + Yahoo, instrument master, OHLCV cache, holidays) | Done | `quantmind/data/` implemented; acceptance passed |
| 2 | Strategy abstraction (TradingStrategy, indicators, parameter sweep, simple backtest) | Done | `quantmind/domain/strategy.py`, `quantmind/indicators/`, `quantmind/backtesting/simple.py`; MA-crossover on RELIANCE works |
| 3 | Vector backtest engine | Done | `quantmind/backtesting/vector.py` + `BacktestRun`; 108 MA variants on RELIANCE in ~1.2 s |
| 4 | Metrics and reporting (30+ metrics, BacktestReport) | Not started | See §9 Phase 4 |
| 5 | Event-driven backtest engine (blotter, slippage, Indian cost model) | Not started | See §9 Phase 5 |
| 6 | Cross-sectional pipelines (Pipeline, Factor, Filter, universe ranking) | Not started | See §9 Phase 6 |
| 7 | Storage and index (.iafbt bundles, SQLite Tier-1, rank_index) | Not started | See §9 Phase 7 |
| 8 | Agent backend (LLM tools, streaming, approval gates) | Not started | See §9 Phase 8 |
| 9 | Chat UI (React + TS + SSE, inline charts, approval cards) | Not started | See §9 Phase 9 |
| 10 | Paper trading with Upstox sandbox (OrderExecutor, portfolio, P&L) | Not started | See §9 Phase 10 |
| 11 | Production hardening (auth, risk controls, audit, disclaimers) | Not started | See §9 Phase 11 |
| 12 | Future expansion (intraday, more brokers, F&O) | Not started | See §9 Phase 12 |

### Next recommended step

Phase 3 is complete (multi-asset vector backtest engine with stop losses, take
profits, trailing stops, cooldowns, costs, and position sizing). Next is **Phase 4**
— metrics and reporting: 30+ backtest metrics and a `BacktestReport` object that can
render equity curves, drawdown charts, monthly heatmaps, and trade tables.

---

## 15. References

- **Reference repository (forked, for parallel study):**
  https://github.com/bezaspace/investing-algorithm-framework
- **Original reference repository:**
  https://github.com/coding-kitties/investing-algorithm-framework
- **Reference framework docs:**
  https://coding-kitties.github.io/investing-algorithm-framework/
- **Reference framework license:** Apache-2.0
- **Upstox API docs:** https://docs.upstox.com/
- **Yahoo Finance library:** https://github.com/ranaroussi/yfinance
