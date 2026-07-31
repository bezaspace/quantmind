# Quantmind — AI-Powered Quant Trading Platform

> A capstone project that wraps the **entire quant hedge-fund workflow behind a single
> AI chat interface**. The user never writes code, opens a notebook, or touches a CLI —
> they describe a strategy in natural language and an AI agent builds it, backtests it
> (vector + event-driven), ranks candidates across parameter sweeps, generates reports,
> and deploys the winner to paper or live trading.
>
> **Reference repository to study while building (forked into our org for parallel
> reference):**
> https://github.com/bezaspace/investing-algorithm-framework
> (origin: https://github.com/coding-kitties/investing-algorithm-framework — 1.6k stars,
> Apache-2.0)

---

## 1. Intention

The goal of Quantmind is **not** to clone the reference repository or import it as a
dependency. The reference repo (`investing-algorithm-framework`) is a well-architected
Python *library* that covers the full quant workflow — strategy definition, vector
backtesting, event-driven simulation, a tiered storage/index layer, 30+ metrics,
cross-sectional pipelines, Monte Carlo permutation testing, HTML reports, and live
trading via CCXT. We study how they built it, then write our own version from scratch,
using their architecture and design patterns as a reference.

What we build on top is fundamentally different in interface and audience:

| Aspect | Reference framework | Quantmind |
|--------|---------------------|-----------|
| Interface | Python code / CLI / HTML report | AI chat (like ChatGPT) |
| User | Developer who writes quant strategies | Anyone who can describe a strategy in English |
| Agent | None (MCP server exists but is optional) | Central — the agent IS the interface |
| Strategy creation | Write a `TradingStrategy` subclass | Describe it in chat; agent generates it |
| Backtest management | Manual CLI / Python calls | Agent runs, ranks, and presents results in chat |
| Reports | Standalone HTML file | Inline in chat + optional full HTML report |
| Deployment | CLI commands | Agent deploys on request |

**Why this project lands jobs:**

- "AI agent operates a complex domain toolchain" is one of the most valuable agent
  categories right now (cf. Devin, Cursor, OpenAI Operator). Wrapping a *quant* workflow
  is a particularly strong demo because the domain is rigorous, the metrics are
  objective, and the results are visual and concrete.
- Building it *well* forces you to demonstrate **AI agent architecture**, **quantitative
  analysis**, **system design**, **data engineering**, and **full-stack engineering** in
  one coherent product — five distinct hiring-relevant skill dimensions, each backed by
  code you can show and design decisions you can defend.
- The "from scratch" approach for the quant engine (not importing the reference library)
  means you can explain *why* every architectural decision was made — exactly what senior
  quant/AI-engineering interviews probe.
- It produces a single, demoable artifact: type a sentence → watch a backtest run → see
  ranked results and charts inline → approve deployment. That is a portfolio piece, not a
  notebook.

The build is intentionally **flexible** — there is no rigid file structure prescribed
here. You retain full autonomy over how to organize the code as you build. What follows
is the architecture, the feature set, and the skill each feature demonstrates.

---

## 2. Architecture overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Chat UI (React + TypeScript)                      │
│  User types natural language → AI responds with results inline      │
│  Strategy summaries · equity curves · drawdowns · trade lists       │
│  Ranked candidate tables · approval cards · deployment status       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ SSE / REST
┌──────────────────────────────▼──────────────────────────────────────┐
│                       Agent Backend (Python)                         │
│   LLM reasoning + tool calling + streaming + human-in-the-loop      │
│   Interprets user intent → calls quant engine tools → renders       │
│   results back into the chat                                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                  Quant Engine  (built from scratch)                  │
│  Strategy · Vector BT · Event BT · Metrics · Storage/Index          │
│  Ranking · Cross-sectional pipelines · Monte Carlo · Reports        │
│  Deployment · (inspired by investing-algorithm-framework             │
│   architecture, written from scratch — not imported)                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
        ┌──────────────┬───────┴────────┬───────────────┐
        ▼              ▼                ▼               ▼
   Market Data      Backtest        Live Trading    Report
   (CCXT / custom   Storage         (CCXT / custom  (HTML /
    providers)      (SQLite index +  OrderExecutor)  inline JSON)
                   content-addressed
                   OHLCV dedup)
```

### The flow of a single chat-driven run

1. **Interpret** — the user types a natural-language request ("Build me a trend-following
   strategy for BTC and ETH with a 5% trailing stop loss"). The agent parses intent into
   a structured strategy spec.
2. **Generate strategy** — the agent constructs a `TradingStrategy` object (or parameter
   sweep range) from the spec, using the quant engine's strategy abstraction.
3. **Backtest** — the agent runs the strategy through the appropriate engine:
   - **Vector backtest** for fast parameter sweeps across thousands of variants (Polars
     or NumPy vectorized signal evaluation).
   - **Event-driven backtest** for realistic bar-by-bar simulation with slippage, partial
     fills, and a full simulation blotter.
4. **Rank** — results land in the backtest storage layer (SQLite index for sub-100ms
   ranking over 10k+ backtests). The agent ranks candidates by the user's chosen metric
   (Sharpe, Sortino, Calmar, etc.).
5. **Analyze** — the agent computes 30+ metrics (CAGR, Sharpe, Sortino, Calmar, VaR,
   CVaR, Max DD, Recovery, win rate, profit factor, consistency), runs Monte Carlo
   permutation testing for statistical robustness, and generates a `BacktestReport`.
6. **Present** — results render inline in the chat: equity curves, drawdowns, trade
   lists, monthly returns, ranked candidate tables. The agent narrates the findings in
   natural language.
7. **Approve** — for any mutating or live action (deploy to paper/live trading), the
   agent pauses and surfaces an approval card. The user approves/edits/rejects.
8. **Deploy** — on approval, the agent deploys the winning strategy via the live trading
   layer (CCXT integration, custom `OrderExecutor` protocol, portfolio persistence).
9. **Persist** — strategies, backtest results, and market data are cached/deduplicated so
   follow-up questions ("now sweep RSI from 14 to 28") reuse prior work.

Every step streams progress to the chat via SSE. Long-running backtests emit progress
events so the user sees the sweep advancing.

---

## 3. Features and the skill each demonstrates

Each feature below is mapped to the component in the reference repository it is inspired
by, so you can always go back to
https://github.com/bezaspace/investing-algorithm-framework for the canonical
implementation pattern while building your own version from scratch.

### 3.1 From-scratch quant engine core
**What:** Build the quant engine primitives yourself — `TradingStrategy` class (declarative
strategy definition with buy/sell signal generation, position sizing, stop losses, take
profits, scaling rules, cooldowns, trading costs), `DataProvider` abstraction, and the
shared strategy abstraction that runs unchanged across vector backtest, event-driven
backtest, and live trading.

**Reference:** `investing_algorithm_framework/domain/strategy.py`,
`domain/data_provider.py`, `domain/order_executor.py`.

**Job skill:** Proves you understand *how* a quant framework works internally — strategy
abstraction, signal generation, position sizing — not just how to call a library. This is
the foundation that makes everything else defensible in an interview.

### 3.2 Vector backtesting engine
**What:** A Polars-powered (or NumPy) vectorized signal evaluation engine for fast
parameter sweeps across thousands of variants. Same strategy class runs here, in
event-driven mode, and live — only the execution context changes.

**Reference:** `investing_algorithm_framework/domain/backtesting/` (vector engine).

**Job skill:** Vectorized backtesting is the workhorse of quant research. Demonstrates
numerical computing, vectorization, and the engineering judgment to know when vector BT
suffices vs. when you need event-driven simulation.

### 3.3 Event-driven backtesting engine
**What:** Bar-by-bar simulation with pluggable slippage and fill models, partial fills,
and a complete simulation blotter. Used for realistic validation of vector-BT winners.

**Reference:** `investing_algorithm_framework/domain/backtesting/` (event-driven engine),
`domain/blotter.py`.

**Job skill:** Event-driven simulation is what separates toy backtests from
production-grade ones. Shows you understand execution realism, slippage modeling, and the
gap between backtest and live performance.

### 3.4 Backtest storage and indexing layer
**What:** A tiered storage architecture — Tier-1 SQLite index for sub-100ms ranking over
10k+ backtests, a swappable `BacktestStore` protocol, and content-addressed OHLCV
deduplication so market data is never fetched or stored twice.

**Reference:** `investing_algorithm_framework/services/backtest_index/`,
`services/backtest_store/`, `infrastructure/database/`.

**Job skill:** System design for high-volume research data. Content-addressed dedup and
tiered indexing are real production patterns. This is the "data engineering" signal.

### 3.5 Performance metrics (30+)
**What:** CAGR, Sharpe, Sortino, Calmar, VaR, CVaR, Max Drawdown, Recovery Factor, win
rate, profit factor, consistency score — computed correctly with edge-case handling
(division by zero, single-trade strategies, etc.).

**Reference:** `investing_algorithm_framework/services/metrics/`.

**Job skill:** Quantitative analysis. Computing these metrics *correctly* (not just
calling a library) is a quant-engineering competency. Interviewers will ask how you
handle annualization, downside deviation, and the corner cases.

### 3.6 Cross-sectional pipelines and factor tables
**What:** Rank, filter, and score entire universes of symbols every iteration using
factor tables. Enables cross-sectional strategies (e.g. "long the top 20% by momentum,
rebalanced weekly").

**Reference:** `investing_algorithm_framework/domain/pipeline/`.

**Job skill:** Cross-sectional analysis is a step up from single-asset backtesting. Shows
portfolio-level thinking and factor-model awareness.

### 3.7 Monte Carlo permutation testing
**What:** Statistical robustness checks across randomized market scenarios — shuffle
trade order, resample returns, and compute the distribution of outcomes to test whether
a strategy's edge is real or an artifact of sequence luck.

**Reference:** `investing_algorithm_framework/` (permutation testing module).

**Job skill:** Statistical rigor. "I permutation-tested my strategy" is the difference
between a credible backtest and a curve-fit one. This is what a quant interviewer wants
to hear.

### 3.8 BacktestReport generation
**What:** Self-contained HTML dashboard with equity curves, drawdowns, trade lists,
monthly returns, and strategy comparison. Also renderable as inline JSON/charts in the
chat for quick lookups.

**Reference:** `investing_algorithm_framework/` (BacktestReport module).

**Job skill:** Data visualization and reporting. A good report turns numbers into a
decision — shows you can communicate results, not just compute them.

### 3.9 Live trading and deployment
**What:** CCXT integration for crypto exchanges, a custom `OrderExecutor` protocol,
portfolio persistence, and deployment targets (AWS Lambda / Azure Functions / long-running
process). The same `TradingStrategy` class that ran in backtest now runs live.

**Reference:** `investing_algorithm_framework/domain/order_executor.py`,
`infrastructure/order_executors/`, `services/order_service/`,
`services/portfolios/`, `services/positions/`.

**Job skill:** Production trading systems. Going from backtest to live is where most
strategies fail. Demonstrates execution-layer engineering, order management, and
portfolio state persistence.

### 3.10 AI chat agent (the interface)
**What:** An LLM agent with domain-specific tools (strategy creation, backtest execution,
ranking, report generation, deployment), system-prompt engineering for quant workflows,
streaming responses, tool calling, and human-in-the-loop approval for any mutating/live
action. The agent IS the user interface — there is no other UI for the quant engine.

**Reference:** The reference framework exposes an MCP server so AI agents can query
backtests and rank strategies. Quantmind goes further: the agent is the primary
interface, not an optional add-on.

**Job skill:** AI agent architecture — the core of the project. Tool calling, streaming,
intent-to-structured-spec parsing, and approval gates are exactly the patterns
interviewers for AI-engineering roles probe.

### 3.11 Chat UI (React + TypeScript)
**What:** A ChatGPT-style chat interface where the user types natural language and the
agent responds with text, inline charts (equity curves, drawdowns), ranked candidate
tables, approval cards, and deployment status. Streaming via SSE.

**Job skill:** Full-stack engineering. Building a real-time chat UI that renders rich
domain content (charts, tables, approval flows) — not just text — is the difference
between a demo and a product.

### 3.12 Two-stage cost optimization (optional/stretch)
**What:** A cheap model triages user intent and simple strategy specs; only complex
spec generation and result analysis hits the strong model. Target significant inference
cost reduction vs. naive single-model runs.

**Job skill:** Cost is the #1 blocker for agent products. Being able to quantify "this
design cut cost X%" is a standout resume line.

---

## 4. Topic coverage matrix

Confirms Quantmind exercises the full surface of the reference repository. Revisit
https://github.com/bezaspace/investing-algorithm-framework for the canonical
implementation of each row while building.

| Reference repo component | Quantmind feature | Section |
|--------------------------|-------------------|---------|
| `TradingStrategy` class | Strategy abstraction (runs in BT + live) | 3.1 |
| `DataProvider` | Market data integration (CCXT / custom) | 3.1 |
| `OrderExecutor` | Live trading + deployment | 3.9 |
| Vector backtesting engine | Vectorized parameter sweeps | 3.2 |
| Event-driven backtesting engine | Bar-by-bar simulation with slippage | 3.3 |
| `blotter.py` | Simulation blotter | 3.3 |
| Backtest index (SQLite Tier-1) | Storage + sub-100ms ranking | 3.4 |
| BacktestStore protocol | Swappable storage layer | 3.4 |
| Content-addressed OHLCV dedup | Market data deduplication | 3.4 |
| Metrics service (30+) | Performance metrics | 3.5 |
| Cross-sectional pipelines | Factor tables + universe ranking | 3.6 |
| Permutation testing | Monte Carlo robustness checks | 3.7 |
| BacktestReport | HTML + inline chat reports | 3.8 |
| CCXT integration + order executors | Live trading | 3.9 |
| Portfolio/position services | Portfolio persistence | 3.9 |
| MCP server (optional in reference) | AI agent as primary interface | 3.10 |
| (not in reference — our addition) | Chat UI (React + TS) | 3.11 |
| (not in reference — our addition) | Two-stage cost optimization | 3.12 |

---

## 5. The interview story (one paragraph)

> "I built an AI-powered quant trading platform where the user operates a full hedge-fund
> workflow through a chat interface — no code, no notebooks. An LLM agent parses
> natural-language strategy descriptions, generates a typed strategy spec, runs vector
> backtests across thousands of parameter variants, validates winners in event-driven
> simulation with slippage modeling, ranks candidates across 30+ metrics (Sharpe, Sortino,
> Calmar, VaR, CVaR, Max DD), runs Monte Carlo permutation testing for statistical
> robustness, presents equity curves and drawdowns inline in the chat, and deploys the
> winner to paper or live trading via CCXT — with human approval gates before any live
> action. The quant engine is built from scratch (strategy abstraction, vector + event-
> driven backtest engines, tiered SQLite storage with content-addressed OHLCV dedup,
> cross-sectional factor pipelines), inspired by but not importing the
> investing-algorithm-framework architecture."

That single paragraph demonstrates five distinct, hiring-relevant skill dimensions — AI
agent architecture, quantitative analysis, system design, data engineering, and
full-stack engineering — each backed by code you can show and design decisions you can
defend.

---

## 6. Build philosophy and guardrails

- **From scratch first.** Build the quant engine primitives yourself before building the
  chat agent on top. The reference repository is a *study reference*, not a dependency.
  Do not `pip install investing-algorithm-framework`. Read their code, understand the
  patterns, and write your own. This is the source of interview-defensible depth.
- **The reference repo is forked into our org for parallel reference.** Use
  https://github.com/bezaspace/investing-algorithm-framework to read the canonical
  implementation of any component while building your own version. Keep it open in a
  browser tab. Cite which file/module you studied in commit messages and PR descriptions.
- **The agent is the interface.** There is no separate quant CLI or notebook UI for the
  user. Every quant operation is reachable through chat. The agent's tool layer wraps the
  quant engine; the user never calls the engine directly.
- **Same strategy class, three contexts.** The `TradingStrategy` abstraction runs
  unchanged in vector backtest, event-driven backtest, and live trading. Only the
  execution context changes. This is a core design constraint — do not fork the strategy
  class per context.
- **Approval before mutation.** Any action that touches live trading, real money, or
  irreversible state requires a human approval gate. Read-only actions (backtest, rank,
  report) run without approval.
- **Demoable milestones.** Every milestone should produce something the user can see in
  the chat. Track cost, latency, and backtest accuracy from day one.
- **Markets: start with crypto via CCXT.** Crypto has free, unified market data and
  testnet/paper trading. Indian stocks (Upstox) and US equities are deferred to later
  phases. This is a scoping decision, not a permanent limitation.
- **Live trading in v1: paper only.** v1 supports paper trading (testnet) via CCXT. Real
  money deployment is gated behind explicit configuration and a second approval layer.
  This is a safety guardrail, not a technical limitation.

---

## 7. What's decided vs. open

### Decided
- **The product:** an AI chat app for quant trading (not voice, not a library, not a CLI).
- **The approach:** build the quant engine from scratch using the
  investing-algorithm-framework's architecture as reference (not importing it).
- **The interface:** chat-based, like ChatGPT — user types, agent does the rest.
- **The scope:** full quant workflow — strategy creation, backtesting (vector +
  event-driven), analysis, ranking, deployment.
- **First markets:** crypto via CCXT (free data, testnet paper trading).
- **Live trading in v1:** paper/testnet only; real money deferred.
- **Reference repo:** forked to
  https://github.com/bezaspace/investing-algorithm-framework for parallel study.

### Open (to decide during the build)
- Agent layer tech stack: LangGraph? custom? which LLM provider? (LangGraph is the
  likely choice — model-agnostic, native tool calling, streaming, human-in-the-loop
  interrupts — matching the pattern used in the Brax project.)
- Chat UI framework: React + Vite (likely, for consistency with Brax/Atlas) vs. Next.js.
- Charting library for inline results: Recharts? ECharts? lightweight-charts?
- How much of the reference framework's feature set to build in v1 vs. defer.
- How the agent presents backtest results in chat: inline charts (rendered client-side
  from JSON) vs. generated images vs. embedded HTML.
- Monetization model (if any) — out of scope for the portfolio build.

---

## 8. Suggested build order (MVP first, then layers)

1. **Quant engine core** — `TradingStrategy`, `DataProvider`, market data via CCXT
   (crypto), vector backtest engine. Single strategy, single asset, no sweeps yet.
   → *Demo: "backtest a simple moving-average strategy on BTC" returns metrics.*
2. **Metrics + storage** — 30+ metrics, SQLite backtest index, content-addressed OHLCV
   dedup. Run and rank a small parameter sweep.
   → *Demo: "sweep the MA window from 10 to 50, rank by Sharpe" returns a ranked table.*
3. **Event-driven backtest** — bar-by-bar simulation, slippage, blotter. Validate a
   vector-BT winner realistically.
   → *Demo: "validate the top strategy in event-driven mode with 0.1% slippage".*
4. **Agent backend** — LLM agent with tools wrapping the quant engine, streaming, intent
   parsing. First chat-driven end-to-end run.
   → *Demo: type a strategy description in chat → agent builds, backtests, ranks, responds.*
5. **Chat UI** — React + TS + SSE, inline charts, ranked tables, streaming responses.
   → *Demo: full chat interface with visual results.*
6. **Cross-sectional pipelines + Monte Carlo** — universe ranking, factor tables,
   permutation testing.
   → *Demo: "rank the top 20 crypto assets by momentum, backtest a long-top-5 strategy,
   permutation-test it".*
7. **Reports** — `BacktestReport` HTML generation + inline chat rendering.
8. **Live/paper trading + deployment** — CCXT testnet, `OrderExecutor`, portfolio
   persistence, approval gates.
   → *Demo: "deploy the top strategy to Binance testnet paper trading".*
9. **Two-stage cost optimization** (optional/stretch).
10. **Docker deployment** — one command up.

Every milestone should be demoable on its own. Track cost, latency, and backtest
accuracy from day one.

---

## 9. Reference

- **Reference repository (forked, for parallel study):**
  https://github.com/bezaspace/investing-algorithm-framework
- **Original reference repository:**
  https://github.com/coding-kitties/investing-algorithm-framework
- **Reference framework docs:**
  https://coding-kitties.github.io/investing-algorithm-framework/
- **Reference framework license:** Apache-2.0
- **Project page (Obsidian):** `Career/Portfolio Projects/Quantmind.md`
- **ATC tracking:** Career → Potential Projects (Quantmind), to be promoted to
  Career → Initiatives on build start.
