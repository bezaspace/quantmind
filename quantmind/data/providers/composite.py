"""Composite data providers that chain or fall back across multiple sources."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Sequence

import polars as pl

from quantmind.domain.exceptions import DataProviderError

from .base import DataProvider


class ChainedDataProvider(DataProvider):
    """Try a list of providers in order and return the first successful result."""

    name = "CHAINED"

    def __init__(self, providers: Sequence[DataProvider]):
        self.providers = providers
        # Use the first provider's cache as the shared cache
        self.cache = providers[0].cache if providers else None

    def resolve_instrument(self, symbol: str, exchange: str = "NSE") -> dict:
        for provider in self.providers:
            try:
                return provider.resolve_instrument(symbol, exchange)
            except DataProviderError:
                continue
        raise DataProviderError(
            f"No provider could resolve {symbol} on {exchange}"
        )

    def get_ohlcv(
        self,
        symbol: str,
        interval: str | object,
        start: Optional[date | datetime] = None,
        end: Optional[date | datetime] = None,
        exchange: str = "NSE",
    ) -> pl.DataFrame:
        last_error: Optional[Exception] = None
        for provider in self.providers:
            try:
                return provider.get_ohlcv(symbol, interval, start, end, exchange)
            except DataProviderError as exc:
                last_error = exc
                continue
        raise DataProviderError(
            f"All providers failed for {symbol}: {last_error}"
        )
