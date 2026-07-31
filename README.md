# Quantmind

An AI-powered quant trading platform where the user operates a full hedge-fund workflow
through a chat interface. No code, no notebooks, no CLI — describe what you want in
natural language and the AI agent builds strategies, runs backtests, analyzes results,
ranks candidates, and deploys the winner.

## Status

Idea — inspiration identified, architecture direction clear, build not started.

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the full intention, architecture, feature/skill
mapping, and build order.

## Reference repository

The quant engine is built from scratch, inspired by (but not importing) the
[investing-algorithm-framework](https://github.com/coding-kitties/investing-algorithm-framework)
architecture. A fork is maintained in our org for parallel study:
https://github.com/bezaspace/investing-algorithm-framework

## Architecture (preliminary)

```
Chat UI (React + TS)  →  Agent Backend (Python, LLM + tools)  →  Quant Engine (from scratch)
                                                                  →  Market Data (CCXT)
                                                                  →  Backtest Storage (SQLite index)
                                                                  →  Live Trading (CCXT)
```

See [PROJECT_PLAN.md](PROJECT_PLAN.md) §2 for the full architecture diagram and the flow
of a single chat-driven run.
