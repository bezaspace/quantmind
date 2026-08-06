"""Upstox data provider for NSE/BSE OHLCV data."""

from __future__ import annotations

import gzip
import logging
import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import httpx
import polars as pl
from dateutil.relativedelta import relativedelta

from quantmind.data.cache import OHLCVCache
from quantmind.domain.exceptions import (
    ConfigurationError,
    DataProviderError,
    SymbolNotFound,
)
from quantmind.domain.models import Interval

from .base import DataProvider

logger = logging.getLogger(__name__)


class UpstoxDataProvider(DataProvider):
    """OHLCV provider backed by the Upstox v2 API.

    Supports 1m/30m/day/week/month candles. Downloads the Upstox instrument
    master to map symbols to ``instrument_key`` values and caches it locally.
    """

    name = "UPSTOX"
    supported_intervals = {
        Interval.MINUTE_1,
        Interval.MINUTE_30,
        Interval.DAY,
        Interval.WEEK,
        Interval.MONTH,
    }

    BASE_URL = "https://api.upstox.com/v2"
    INSTRUMENT_URL = (
        "https://assets.upstox.com/market-quote/instruments/exchange/{exchange}.json.gz"
    )

    def __init__(
        self,
        access_token: Optional[str] = None,
        cache: Optional[OHLCVCache] = None,
        request_delay: float = 0.05,
    ):
        logger.debug("UpstoxDataProvider init")
        super().__init__(cache=cache)
        self.access_token = access_token or os.getenv("UPSTOX_ANALYTICS_TOKEN")
        if not self.access_token:
            raise ConfigurationError(
                "Upstox access token is required. Set UPSTOX_ANALYTICS_TOKEN."
            )
        self.request_delay = request_delay
        self._http = httpx.Client(
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        self._instrument_lookup: dict[tuple[str, str], dict] = {}
        self._instrument_loaded: set[str] = set()

    def resolve_instrument(self, symbol: str, exchange: str = "NSE") -> dict:
        """Return the Upstox instrument record for a symbol."""
        exchange = exchange.upper()
        key = symbol.upper()
        if exchange not in self._instrument_loaded:
            self._load_instruments(exchange)
        result = self._instrument_lookup.get((exchange, key))
        if result is None:
            raise SymbolNotFound(
                f"Could not resolve {key} on {exchange}. "
                "Check the trading symbol or exchange."
            )
        return result

    def get_ohlcv(
        self,
        symbol: str,
        interval: str | Interval,
        start: Optional[date | datetime] = None,
        end: Optional[date | datetime] = None,
        exchange: str = "NSE",
    ) -> pl.DataFrame:
        """Fetch historical OHLCV from Upstox, chunked to match API limits."""
        logger.debug("get_ohlcv start %s %s", symbol, interval)
        interval = self._validate_interval(interval)
        logger.debug("interval validated %s", interval)
        start, end = self._normalise_dates(start, end)
        logger.debug("dates normalised %s %s", start, end)
        instrument = self.resolve_instrument(symbol, exchange)
        instrument_key = instrument["instrument_key"]
        logger.debug("instrument_key %s", instrument_key)

        chunks = self._date_chunks(start, end, interval)
        logger.debug("chunks %d", len(chunks))
        frames: list[pl.DataFrame] = []

        for chunk_start, chunk_end in chunks:
            logger.debug("chunk %s to %s", chunk_start, chunk_end)
            cached = self.cache.get(
                self.name, symbol, interval.value, chunk_start, chunk_end
            )
            if cached is not None:
                logger.debug("cache hit")
                frames.append(cached)
                continue

            url = (
                f"{self.BASE_URL}/historical-candle/"
                f"{instrument_key}/{interval.value}/"
                f"{chunk_end.isoformat()}/{chunk_start.isoformat()}"
            )
            logger.debug("requesting %s", url)
            response = self._http.get(url)
            logger.debug("response status %s", response.status_code)
            if response.status_code == 429:
                raise DataProviderError(
                    "Upstox rate limit exceeded. Retry later or use Yahoo Finance fallback."
                )
            if response.status_code != 200:
                raise DataProviderError(
                    f"Upstox API error {response.status_code}: {response.text}"
                )

            payload = response.json()
            data = payload.get("data", {}).get("candles", [])
            frame = self._candles_to_frame(data)
            if len(frame) == 0:
                frame = self._empty_frame()

            self.cache.set(
                self.name, symbol, interval.value, chunk_start, chunk_end, frame
            )
            frames.append(frame)
            if self.request_delay:
                time.sleep(self.request_delay)

        if not frames:
            return self._empty_frame()

        combined = pl.concat(frames).unique(subset=["Datetime"], keep="first")
        combined = combined.sort("Datetime")

        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())
        combined = combined.filter(
            (pl.col("Datetime") >= start_dt) & (pl.col("Datetime") <= end_dt)
        )
        return combined

    def _load_instruments(self, exchange: str) -> None:
        """Download and cache the Upstox instrument master for an exchange."""
        logger.debug("_load_instruments start %s", exchange)
        exchange = exchange.upper()
        instrument_dir = self.cache.cache_dir / "instruments"
        instrument_dir.mkdir(parents=True, exist_ok=True)
        local_path = instrument_dir / f"{exchange}.json"

        if not local_path.exists():
            logger.debug("downloading instrument master %s", exchange)
            url = self.INSTRUMENT_URL.format(exchange=exchange)
            with self._http.stream("GET", url, timeout=120.0) as response:
                response.raise_for_status()
                raw = b"".join(response.iter_raw())
            data = json.loads(gzip.decompress(raw))
            local_path.write_text(json.dumps(data))
        else:
            logger.debug("reading cached instrument master %s", exchange)
            data = json.loads(local_path.read_text())

        logger.debug("building lookup %s", exchange)
        segment = f"{exchange}_EQ"
        for instrument in data:
            if instrument.get("segment") != segment:
                continue
            if instrument.get("instrument_type") != "EQ":
                continue
            trading_symbol = instrument.get("trading_symbol", "").upper()
            if trading_symbol:
                self._instrument_lookup[(exchange, trading_symbol)] = instrument
        self._instrument_loaded.add(exchange)
        logger.debug("_load_instruments done %s", exchange)

    @staticmethod
    def _candles_to_frame(candles: list) -> pl.DataFrame:
        """Convert Upstox candle array to a Polars DataFrame."""
        rows = []
        for candle in candles:
            ts, open_, high, low, close, volume, _oi = candle
            rows.append(
                {
                    "Datetime": datetime.fromisoformat(ts).replace(tzinfo=None),
                    "Open": float(open_),
                    "High": float(high),
                    "Low": float(low),
                    "Close": float(close),
                    "Volume": int(volume),
                }
            )

        if not rows:
            return UpstoxDataProvider._empty_frame()

        return pl.DataFrame(
            rows,
            schema={
                "Datetime": pl.Datetime("ns"),
                "Open": pl.Float64,
                "High": pl.Float64,
                "Low": pl.Float64,
                "Close": pl.Float64,
                "Volume": pl.Int64,
            },
            orient="row",
        )

    @staticmethod
    def _empty_frame() -> pl.DataFrame:
        return pl.DataFrame(
            schema={
                "Datetime": pl.Datetime("ns"),
                "Open": pl.Float64,
                "High": pl.Float64,
                "Low": pl.Float64,
                "Close": pl.Float64,
                "Volume": pl.Int64,
            }
        )

    @staticmethod
    def _date_chunks(
        start: date, end: date, interval: Interval
    ) -> list[tuple[date, date]]:
        logger.debug("_date_chunks start %s %s %s", start, end, interval)
        """Break a date range into chunks that fit Upstox API limits.

        Empirically validated maximum lookback ranges:
        - 1-minute: 30 calendar days
        - 30-minute: 90 calendar days
        - day/week/month: 10 years
        """
        if interval == Interval.MINUTE_1:
            delta = relativedelta(days=30)
        elif interval == Interval.MINUTE_30:
            delta = relativedelta(days=90)
        else:
            delta = relativedelta(years=10)

        if start == end:
            return [(start, end)]

        chunks: list[tuple[date, date]] = []
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + delta, end)
            chunks.append((cursor, chunk_end))
            if chunk_end == end:
                break
            cursor = chunk_end
        return chunks
