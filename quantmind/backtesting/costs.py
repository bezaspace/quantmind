"""Cost models and slippage for event-driven backtesting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class CostBreakdown:
    brokerage: float
    stt: float
    stamp_duty: float
    transaction_charges: float
    sebi_charges: float
    gst: float
    total: float


class IndianEquityCostModel:
    """Indian equity delivery (CNC) cost model.

    Approximate charges for NSE/BSE delivery trades:
    - Brokerage: configurable flat or percentage
    - STT (Securities Transaction Tax): 0.1% on sell-side only
    - Stamp duty: 0.015% on buy-side only
    - Transaction charges: ~0.00325% on both sides
    - SEBI turnover fee: ₹10 per crore of turnover (0.0001%)
    - GST: 18% on brokerage + transaction charges

    These are defaults and can be overridden. Stamp/SEBI/transaction charges
    change over time; use current values when live trading.
    """

    def __init__(
        self,
        brokerage_pct: float = 0.0,
        brokerage_flat: float = 0.0,
        stt_pct_sell: float = 0.1,
        stamp_duty_pct_buy: float = 0.015,
        transaction_charge_pct: float = 0.00325,
        gst_pct: float = 18.0,
        sebi_per_crore: float = 10.0,
        slippage_pct: float = 0.05,
    ):
        self.brokerage_pct = brokerage_pct
        self.brokerage_flat = brokerage_flat
        self.stt_pct_sell = stt_pct_sell
        self.stamp_duty_pct_buy = stamp_duty_pct_buy
        self.transaction_charge_pct = transaction_charge_pct
        self.gst_pct = gst_pct
        self.sebi_per_crore = sebi_per_crore
        self.slippage_pct = slippage_pct

    def calculate(self, turnover: float, side: str) -> CostBreakdown:
        """Return per-side charges for the given turnover."""
        side_upper = side.upper()

        if self.brokerage_pct:
            brokerage = max(self.brokerage_flat, turnover * self.brokerage_pct / 100)
        else:
            brokerage = self.brokerage_flat

        stt = turnover * self.stt_pct_sell / 100 if side_upper == "SELL" else 0.0
        stamp_duty = turnover * self.stamp_duty_pct_buy / 100 if side_upper == "BUY" else 0.0
        transaction_charges = turnover * self.transaction_charge_pct / 100
        sebi_charges = turnover * (self.sebi_per_crore / 1e7)  # 1 crore = 10,000,000
        gst = (brokerage + transaction_charges) * self.gst_pct / 100

        total = brokerage + stt + stamp_duty + transaction_charges + sebi_charges + gst

        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            stamp_duty=stamp_duty,
            transaction_charges=transaction_charges,
            sebi_charges=sebi_charges,
            gst=gst,
            total=total,
        )

    def get_buy_fill_price(self, price: float) -> float:
        return price * (1 + self.slippage_pct / 100)

    def get_sell_fill_price(self, price: float) -> float:
        return price * (1 - self.slippage_pct / 100)

    def apply_buy(self, price: float, quantity: float) -> Tuple[float, float, CostBreakdown]:
        """Return fill price, gross value, and cost breakdown for a buy."""
        fill_price = self.get_buy_fill_price(price)
        turnover = fill_price * quantity
        cost = self.calculate(turnover, "BUY")
        return fill_price, turnover + cost.total, cost

    def apply_sell(self, price: float, quantity: float) -> Tuple[float, float, CostBreakdown]:
        """Return fill price, net proceeds, and cost breakdown for a sell."""
        fill_price = self.get_sell_fill_price(price)
        turnover = fill_price * quantity
        cost = self.calculate(turnover, "SELL")
        return fill_price, turnover - cost.total, cost
