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

## Phase 1 acceptance

- Fetch and cache 5 years of RELIANCE daily data from Upstox in <2 seconds from cache.
- 1-minute and 30-minute candles are fetched via automatic chunked requests.
- 13 unit tests pass.
