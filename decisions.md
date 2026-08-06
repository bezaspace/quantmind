# QuantMind Decisions Log

A running record of important design and implementation decisions. Keep entries short and include the date and rationale.

---

## 2026-08-06 — Phase 1 (Indian market data layer)

### 1. Upstox v2 as the primary data source
- **Decision:** Use the Upstox v2 REST API for NSE/BSE OHLCV data.
- **Rationale:** Free, well-documented, and the `UPSTOX_ANALYTICS_TOKEN` secret is already available. The bearer token works directly against `https://api.upstox.com/v2`.

### 2. Instrument master from `assets.upstox.com`
- **Decision:** Download the exchange-level instrument master from `https://assets.upstox.com/market-quote/instruments/exchange/{exchange}.json.gz` and cache it as uncompressed JSON.
- **Rationale:** The gzipped per-exchange files are small (~2 MB for NSE, ~0.8 MB for BSE), update daily around 6 AM, and contain both `instrument_key` and `trading_symbol` needed for symbol resolution.

### 3. Chunked historical-candle requests
- **Decision:** Split `get_ohlcv` requests into chunks based on empirically validated Upstox limits:
  - 1-minute: 30 calendar days per request
  - 30-minute: 90 calendar days per request
  - day / week / month: up to 10 years per request
- **Rationale:** Upstox returns `UDAPI1148` / `UDAPI1020` for oversized ranges. Chunking avoids these errors and respects rate limits.

### 4. Yahoo Finance as a fallback, not a replacement
- **Decision:** Implement `YahooFinanceDataProvider` and `ChainedDataProvider` so Upstox is tried first; Yahoo Finance is used only if Upstox fails or does not support an interval.
- **Rationale:** Yahoo provides multi-year daily/weekly/monthly history in a single request, but its intraday coverage is limited. A chain keeps the most accurate Upstox path first while giving a safe fallback.

### 5. Polars DataFrames as the internal OHLCV format
- **Decision:** Return `pl.DataFrame` with columns `Datetime, Open, High, Low, Close, Volume` and store cache blobs as Parquet.
- **Rationale:** Polars is fast, memory-efficient, and handles the acceptance target of sub-2-second cache reads for 5 years of daily data. Parquet preserves types.

### 6. Naive local timestamps
- **Decision:** Parse Upstox timestamps (`+05:30`) and store them as naive IST datetimes.
- **Rationale:** Avoids date shifts when converting daily candles (`00:00:00+05:30`) to UTC. All backtests will run on exchange-local time.

### 7. Content-addressed OHLCV cache
- **Decision:** Cache key = SHA-256 of `(provider, symbol, interval, start_date, end_date)`. Store each chunk as a Parquet blob in `~/.quantmind/cache/ohlcv/<hash>.parquet` and keep an SQLite index for fast lookup.
- **Rationale:** Same provider/range/symbol/interval is never downloaded twice; blobs are deduplicated by content hash and can be reused across providers only when intentional.

### 8. NSE calendar from `nse-calendar`
- **Decision:** Use the `nse-calendar` package for NSE holidays and treat BSE holidays as the same set in v1.
- **Rationale:** `nse-calendar` is dependency-light, covers 1996 onwards, and keeps the project from maintaining a brittle holiday list. BSE/NSE holidays overlap enough for a v1 implementation.

### 9. Python 3.10 compatibility
- **Decision:** Set `requires-python = ">=3.10"` in `pyproject.toml`.
- **Rationale:** The current Devin VM runs Python 3.10.12. We can bump to 3.11 later when the environment does.

### 10. No external quant library dependency
- **Decision:** Keep `pandas`, `polars`, `yfinance`, and `nse-calendar` for data and IO only; do not install `investing-algorithm-framework` or any other quant/backtest library.
- **Rationale:** The project is a from-scratch quant engine, so dependencies are limited to data fetching, parsing, and testing.

### 11. Direct push to `main`
- **Decision:** Push commits directly to `main` for Phase 1.
- **Rationale:** Requested by the project owner to keep the repo moving quickly while the project is still solo. Re-evaluate branch protection before Phase 8 (agent backend) or multi-contributor work.

### 12. Logging added to data providers
- **Decision:** Add `logging` debug calls to `UpstoxDataProvider` and cache operations.
- **Rationale:** An infinite-loop bug in `_date_chunks` was hard to spot without visible progress; logging made it trivial to identify and fix.

---

## 2026-08-06 — Phase 2 (Strategy abstraction, indicators, and simple backtest)

### 13. Port and adapt the reference framework, not import it
- **Decision:** Read `investing-algorithm-framework` source and re-implement its proven patterns (`TradingStrategy`, risk rules, cooldown tracker, backtest runner) in `quantmind/`, not install it as a dependency.
- **Rationale:** The user wants the system to look self-built while benefiting from a validated design. Code is adapted to Polars-first, Indian-market defaults.

### 14. Polars-only internal OHLCV pipeline
- **Decision:** `generate_buy_signals`/`generate_sell_signals` receive `dict[str, pl.DataFrame]` and return `dict[str, pl.Series]`. All indicators are implemented in pure Polars.
- **Rationale:** Avoids pandas/polars friction and keeps Phase 3 vectorization natural. `pandas` is still used only for `yfinance` compatibility.

### 15. Lightweight `SimpleBacktest` as a Phase 2 acceptance runner
- **Decision:** Implement a single-asset, bar-by-bar `SimpleBacktest` runner that uses `TradingStrategy` signals, `PositionSize`, `TradingCost`, `StopLossRule`, `TakeProfitRule`, `CooldownRule`, and `ScalingRule`.
- **Rationale:** It proves the strategy abstraction works without building the full multi-asset vector engine planned for Phase 3.

### 16. Indian-market defaults inside `TradingStrategy`
- **Decision:** `market="NSE"`, `product_type="CNC"`, `long_only=True` are class-level defaults.
- **Rationale:** Reduces boilerplate for Indian-equity strategies and enforces long-only in the simple backtest until short selling is explicitly supported.

### 17. Parameter sweep without full backtest engine
- **Decision:** `ParameterGrid` + `sweep(strategy_class, grid, run_backtest)` accepts a user-provided backtest callable.
- **Rationale:** Keeps sweep independent of the runner implementation; works with `SimpleBacktest` today and `VectorBacktest` in Phase 3.

---

## 2026-08-06 — Phase 3 (Vector backtest engine)

### 18. Polars-first multi-asset backtest with pre-aligned arrays
- **Decision:** `VectorBacktest` builds a master `Datetime` index, aligns each symbol's OHLCV and signal series to it, and runs a fast Python loop over pre-extracted lists.
- **Rationale:** Avoids per-bar Polars row lookups; the inner loop works on plain `float`/`bool` lists. For 100 MA-window variants on 1,240 RELIANCE daily bars this completed in ~1.2 s, satisfying the Phase 3 acceptance threshold.

### 19. Microsecond-normalized `Datetime` columns
- **Decision:** `VectorBacktest.run()` casts every input `Datetime` column to `pl.Datetime("us")` before alignment and signal generation.
- **Rationale:** `UpstoxDataProvider` returns `datetime[ns]` while Polars defaults and indicator outputs often produce `datetime[us]`. Normalization prevents join/schema errors without touching provider internals.

### 20. `BacktestResult` / `BacktestRun` / `Backtest` objects
- **Decision:** Introduce a `BacktestResult` base dataclass, a `BacktestRun` subclass with `backtest_id`/`name`, and a `Backtest` configuration container.
- **Rationale:** Satisfies the Phase 3 requirement to return a "`Backtest` object with runs and per-run metrics" and gives Phase 4 reporting a stable result type to extend.

### 21. Trust the backtest engine through deterministic validation
- **Decision:** Add a dedicated `tests/backtesting/test_backtest_accuracy.py` suite with hand-calculated P&L, fee/slippage, stop-loss, take-profit, trailing-stop, and a `VectorBacktest` vs `SimpleBacktest` cross-check.
- **Rationale:** A custom backtester is only as good as the evidence that its arithmetic matches reality. Closed-form tests prove the engine computes the right fills, fees, and exits rather than just producing plausible-looking numbers.

---

## 2026-08-06 — Phase 4 (Metrics and reporting)

### 22. Polars-first metrics library
- **Decision:** Implement 30+ metrics in `quantmind/metrics/core.py` using Polars `Series` operations and pure Python for statistics not exposed by Polars.
- **Rationale:** Metrics are computed from `VectorBacktest` outputs that are already Polars DataFrames. Staying native avoids the `pyarrow`/`to_pandas` conversion issues we hit in `BacktestReport` and keeps the pipeline fast and dependency-light.

### 23. `BacktestReport` renders to JSON, Markdown, and HTML without mandatory plotting dependencies
- **Decision:** `BacktestReport` provides `to_dict`, `to_json`, `to_markdown`, and `to_html`. HTML uses Plotly when installed; otherwise it falls back to simple SVG equity/drawdown charts and self-generated HTML tables.
- **Rationale:** The environment may not have `plotly` or `pyarrow`; the report must still be readable and saveable. Plotly is only a soft dependency.

### 24. Hand-calculated metric tests
- **Decision:** Add `tests/metrics/test_metrics.py` with closed-form checks for `total_return`, `cagr`, `max_drawdown`, `sharpe`, `profit_factor`, `win_rate`, and `monthly_heatmap`.
- **Rationale:** Metrics must be trustworthy. Closed-form tests guarantee that popular metrics like CAGR and drawdown are computed exactly as users would calculate them by hand.

---

## 2026-08-06 — Phase 5 (Event-driven backtest engine)

### 25. Separate `EventDrivenBacktest` with explicit order objects
- **Decision:** Add `EventDrivenBacktest` next to `VectorBacktest`, using `Order`, `ExecutionEngine`, `Portfolio`, and `Position` objects.
- **Rationale:** Event-driven execution is useful for realistic fill simulation, limit/stop orders, and one-bar slippage. A separate class keeps the fast vector engine available for parameter sweeps while the event engine handles precise order semantics.

### 26. Indian-equity delivery cost model
- **Decision:** Implement `IndianEquityCostModel` with STT (sell only), stamp duty (buy only), transaction charges, SEBI turnover fee, GST on brokerage + transaction charges, configurable brokerage, and slippage.
- **Rationale:** Backtests for Indian CNC delivery must account for multiple regulatory/tax costs. Encapsulating them in one model makes it easy to swap defaults and audit total transaction cost per fill.

### 27. One-bar market-order delay
- **Decision:** Market orders generated at the close of bar `t` are filled at the open of bar `t+1`.
- **Rationale:** Prevents lookahead bias. The strategy only sees bar `t` data when deciding; the actual fill occurs on the next bar's open, which is the earliest realistic price.

---

## 2026-08-06 — Phase 6 (Cross-sectional pipelines)

### 28. Declarative `Pipeline` with class-attribute factors/filters
- **Decision:** Implement `Pipeline` base class using `__init_subclass__` to introspect class attributes, mirroring the reference design but with Polars internals. `Filter` is modeled as a subclass of `Factor` so it can participate in `rank(mask=...)` and `universe` declarations.
- **Rationale:** A class-based DSL is expressive for cross-sectional screens and keeps universe definitions co-located with the factors that feed them. Reusing `Factor` for `Filter` avoids duplicating caching and evaluation machinery.

### 29. Long-form panel as the canonical pipeline input
- **Decision:** `PipelineEngine.run()` takes a long-form DataFrame with `datetime`, `symbol`, and lower-case OHLCV columns, and produces a long-form DataFrame of factor values and boolean filters.
- **Rationale:** Polars window/over expressions work naturally on long-form panels. It also makes it trivial to join pipeline output back to per-symbol strategy signals.

### 30. Pipeline-to-strategy bridge
- **Decision:** Add `PipelineMomentumStrategy` in `quantmind/pipeline/strategy_bridge.py` that converts a `Pipeline` ranking into per-symbol boolean buy/sell signals consumable by `VectorBacktest`.
- **Rationale:** Phases 1–5 already had a stable backtest/strategy API. A thin bridge lets pipeline-ranked universes plug directly into the existing `VectorBacktest` without changing the backtest engine.

---

## 2026-08-06 — Phase 7 (Storage and indexing)

### 31. `.iafbt` bundle = zip + JSON + Parquet blobs
- **Decision:** Implement backtest bundles as ZIP archives containing `metadata.json` plus Parquet blobs for `equity_curve` and `trades`. `summary_only=True` reads only the JSON metadata without loading Parquet.
- **Rationale:** No `msgpack`/`zstandard` dependencies are installed, and a zip-with-JSON format is trivial to inspect with standard tools while still deferring heavy series to Parquet.

### 32. SQLite Tier-1 index for backtest runs and factor snapshots
- **Decision:** Add `SQLiteIndex` with `backtest_runs` and `factor_snapshots` tables, and a `RankIndex` helper for top-N factor queries.
- **Rationale:** A small local SQLite index is enough to track hundreds of backtests and daily factor snapshots, supports fast date/factor lookups, and avoids extra server dependencies.

### 33. Content-addressed Tier-1 Parquet store
- **Decision:** Add `Tier1Store` that stores DataFrames as Parquet files keyed by SHA-256 of the descriptor and content hash.
- **Rationale:** Content addressing deduplicates repeated OHLCV/factor writes and gives us a stable lookup key to embed in backtest provenance.

---

## 2026-08-06 — Phase 8 (Agent backend)

### 34. FastAPI + SSE agent backend
- **Decision:** Build the agent backend with FastAPI, exposing `/api/chat`, `/api/chat/stream` (SSE), `/api/approval/{request_id}`, and `/health`. Stream events are JSON payloads over SSE.
- **Rationale:** The frontend (Phase 9) will consume streaming events and approval cards. SSE is simpler than WebSockets for unidirectional server-to-client updates and works well with React's `EventSource`.

### 35. Pluggable LLM client with echo fallback
- **Decision:** Define `LLMClient` ABC with `EchoLLM` (testing/no key) and `OpenAILLM` (OpenAI-compatible) implementations. The agent uses `OPENAI_API_KEY` when present and falls back to echo otherwise.
- **Rationale:** This lets the backend be exercised in tests and demos without a live API key while supporting real LLM calls in production.

### 36. Tool registry and approval gates
- **Decision:** Tools are `Tool` objects registered on `AgentSession`. Tools that mutate state (e.g. `save_backtest_bundle`) require approval. The API emits `approval_requested` events and accepts approvals via `/api/approval/{request_id}`.
- **Rationale:** Human-in-the-loop control for file-writing or order-related actions is a safety primitive; making approval gates explicit keeps the contract clear between agent, UI, and user.

---

## 2026-08-06 — Phase 9 (Chat UI)

### 37. Vite + React + TypeScript chat frontend
- **Decision:** Build the chat UI in `frontend/` as a Vite React TypeScript SPA. It connects to the FastAPI backend via `EventSource` SSE and uses `recharts` for inline result charts.
- **Rationale:** Vite gives fast dev HMR and a production build, React/TS is the standard stack for the reference projects, and SSE is the simplest way to stream agent events to the browser.

### 38. Vite dev proxy to backend
- **Decision:** Configure `vite.config.ts` to proxy `/api` to `http://localhost:8000` and add CORS to the FastAPI app.
- **Rationale:** This lets `npm run dev` serve the UI and talk to the Python backend without cross-origin issues during local development.
