"""Futures & Options support: option chain parsing and contract helpers."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class OptionType(str, Enum):
    CALL = "CE"
    PUT = "PE"


@dataclass
class OptionContract:
    symbol: str
    underlying: str
    expiry: date
    strike: float
    option_type: OptionType
    instrument_token: Optional[str] = None
    ltp: Optional[float] = None
    volume: Optional[float] = None
    oi: Optional[float] = None
    iv: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None

    @property
    def name(self) -> str:
        return f"{self.underlying} {self.expiry.isoformat()} {self.strike} {self.option_type.value}"


def option_chain_from_upstox(raw: Dict[str, Any], underlying: str) -> List[OptionContract]:
    """Parse Upstox v2 option chain response into ``OptionContract`` objects."""
    contracts: List[OptionContract] = []
    data = raw.get("data", {})
    expiry_dates = data.get("expiry_dates", [])
    for exp in expiry_dates:
        for strike in data.get("strike_prices", []):
            for opt in ("CE", "PE"):
                token = f"{underlying}_{exp}_{strike}_{opt}"
                contracts.append(
                    OptionContract(
                        symbol=token,
                        underlying=underlying,
                        expiry=date.fromisoformat(exp) if isinstance(exp, str) else date.today(),
                        strike=float(strike),
                        option_type=OptionType(opt),
                        instrument_token=token,
                    )
                )
    return contracts


def get_option_chain(underlying: str, exchange: str = "NSE") -> List[OptionContract]:
    """Fetch an option chain from Upstox (or return a synthetic chain when unavailable)."""
    token = os.getenv("UPSTOX_ANALYTICS_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN")
    url = f"https://api.upstox.com/v2/option/chain/{exchange}/{underlying}"
    try:
        with httpx.Client(timeout=30.0) as client:
            if token:
                client.headers["Authorization"] = f"Bearer {token}"
            resp = client.get(url)
            resp.raise_for_status()
            return option_chain_from_upstox(resp.json(), underlying)
    except Exception as exc:
        logger.warning("Failed to fetch option chain for %s: %s", underlying, exc)

    # Synthetic chain fallback for development/testing
    return _synthetic_chain(underlying)


def _synthetic_chain(underlying: str, strikes: int = 5) -> List[OptionContract]:
    from datetime import timedelta

    base = 100.0
    expiry = date.today() + timedelta(days=30)
    contracts: List[OptionContract] = []
    for i in range(strikes):
        for opt in (OptionType.CALL, OptionType.PUT):
            token = f"{underlying}_{expiry.isoformat()}_{base + i * 10}_{opt.value}"
            contracts.append(
                OptionContract(
                    symbol=token,
                    underlying=underlying,
                    expiry=expiry,
                    strike=base + i * 10,
                    option_type=opt,
                    instrument_token=token,
                )
            )
    return contracts
