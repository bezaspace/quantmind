"""Risk, sizing, and cost models for strategies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Union


class PositionSize:
    """Defines how much capital to allocate to a specific symbol."""

    def __init__(
        self,
        symbol: str,
        percentage_of_portfolio: Optional[float] = None,
        fixed_amount: Optional[float] = None,
    ):
        self.symbol = symbol.upper()
        self.percentage_of_portfolio = percentage_of_portfolio
        self.fixed_amount = fixed_amount

    def get_size(self, portfolio_value: float, price: float) -> float:
        if self.fixed_amount is not None:
            return self.fixed_amount
        if self.percentage_of_portfolio is not None:
            return portfolio_value * (self.percentage_of_portfolio / 100)
        raise ValueError(
            "PositionSize must have either fixed_amount or percentage_of_portfolio"
        )

    def __repr__(self) -> str:
        return (
            f"PositionSize(symbol={self.symbol}, "
            f"percentage_of_portfolio={self.percentage_of_portfolio}, "
            f"fixed_amount={self.fixed_amount})"
        )


class StopLossRule:
    """Percentage or trailing stop loss attached to a symbol."""

    def __init__(
        self,
        symbol: str,
        percentage_threshold: float,
        sell_percentage: float = 100.0,
        trailing: bool = False,
    ):
        self.symbol = symbol.upper()
        self.percentage_threshold = percentage_threshold
        self.sell_percentage = sell_percentage
        self.trailing = trailing

    def __repr__(self) -> str:
        return (
            f"StopLossRule(symbol={self.symbol}, "
            f"percentage_threshold={self.percentage_threshold}, "
            f"trailing={self.trailing})"
        )


class TakeProfitRule:
    """Percentage or trailing take profit attached to a symbol."""

    def __init__(
        self,
        symbol: str,
        percentage_threshold: float,
        sell_percentage: float = 100.0,
        trailing: bool = False,
    ):
        self.symbol = symbol.upper()
        self.percentage_threshold = percentage_threshold
        self.sell_percentage = sell_percentage
        self.trailing = trailing

    def __repr__(self) -> str:
        return (
            f"TakeProfitRule(symbol={self.symbol}, "
            f"percentage_threshold={self.percentage_threshold}, "
            f"trailing={self.trailing})"
        )


class ScalingRule:
    """Position scaling (pyramiding / trimming) rule for a symbol."""

    def __init__(
        self,
        symbol: str,
        max_entries: int = 1,
        scale_in_percentage: Union[float, List[float]] = 100.0,
        scale_out_percentage: Union[float, List[float]] = 50.0,
        max_position_percentage: Optional[float] = None,
        cooldown_in_bars: int = 0,
    ):
        self.symbol = symbol.upper()
        self.max_entries = max_entries
        self.max_position_percentage = max_position_percentage
        self.cooldown_in_bars = cooldown_in_bars

        self._scale_in_percentages = self._normalize(scale_in_percentage)
        self._scale_out_percentages = self._normalize(scale_out_percentage)

    @staticmethod
    def _normalize(value: Union[float, List[float]]) -> List[float]:
        if isinstance(value, (int, float)):
            return [float(value)]
        return [float(v) for v in value]

    @property
    def scale_in_percentage(self) -> Union[float, List[float]]:
        if len(self._scale_in_percentages) == 1:
            return self._scale_in_percentages[0]
        return list(self._scale_in_percentages)

    @property
    def scale_out_percentage(self) -> Union[float, List[float]]:
        if len(self._scale_out_percentages) == 1:
            return self._scale_out_percentages[0]
        return list(self._scale_out_percentages)

    def get_scale_in_percentage(self, index: int) -> float:
        if index < len(self._scale_in_percentages):
            return self._scale_in_percentages[index]
        return self._scale_in_percentages[-1]

    def get_scale_out_percentage(self, index: int) -> float:
        if index < len(self._scale_out_percentages):
            return self._scale_out_percentages[index]
        return self._scale_out_percentages[-1]

    def __repr__(self) -> str:
        return (
            f"ScalingRule(symbol={self.symbol}, max_entries={self.max_entries}, "
            f"scale_in_percentage={self.scale_in_percentage}, "
            f"scale_out_percentage={self.scale_out_percentage})"
        )


class CooldownTrigger(str, Enum):
    BUY = "buy"
    SELL = "sell"
    ANY = "any"

    @classmethod
    def coerce(cls, value: str) -> "CooldownTrigger":
        if isinstance(value, cls):
            return value
        return cls(value.lower())


class CooldownBlocks(str, Enum):
    BUY = "buy"
    SELL = "sell"
    ANY = "any"

    @classmethod
    def coerce(cls, value: str) -> "CooldownBlocks":
        if isinstance(value, cls):
            return value
        return cls(value.lower())

    def matches(self, side: str) -> bool:
        side = CooldownBlocks.coerce(side)
        if self is CooldownBlocks.ANY:
            return True
        return self is side


class CooldownRule:
    """Declarative cooldown gate for a strategy."""

    def __init__(
        self,
        *,
        symbol: Optional[str] = None,
        trigger: Union[str, CooldownTrigger] = CooldownTrigger.ANY,
        blocks: Union[str, CooldownBlocks] = CooldownBlocks.ANY,
        bars: int = 0,
    ):
        if bars < 0:
            raise ValueError(f"CooldownRule.bars must be >= 0, got {bars}")
        self.symbol = symbol.upper() if symbol else None
        self.trigger = CooldownTrigger.coerce(trigger)
        self.blocks = CooldownBlocks.coerce(blocks)
        self.bars = int(bars)

    @property
    def is_portfolio_scoped(self) -> bool:
        return self.symbol is None

    def applies_to_symbol(self, symbol: str) -> bool:
        return self.is_portfolio_scoped or self.symbol == symbol.upper()

    def trigger_matches(self, order_side: str) -> bool:
        side = CooldownTrigger.coerce(order_side)
        if self.trigger is CooldownTrigger.ANY:
            return True
        return self.trigger is side

    def blocks_signal(self, signal_side: str) -> bool:
        return self.blocks.matches(signal_side)

    def __repr__(self) -> str:
        scope = self.symbol if self.symbol is not None else "<portfolio>"
        return (
            f"CooldownRule(symbol={scope}, trigger={self.trigger.value}, "
            f"blocks={self.blocks.value}, bars={self.bars})"
        )


class CooldownTracker:
    """Runtime helper that decides whether a signal is in cooldown."""

    def __init__(self):
        self._last_event: dict[tuple[Optional[str], CooldownTrigger], int] = {}

    def reset(self) -> None:
        self._last_event.clear()

    def record(
        self,
        *,
        symbol: str,
        order_side: Union[str, CooldownTrigger],
        bar_index: int,
    ) -> None:
        side = CooldownTrigger.coerce(order_side)
        for scope in (symbol.upper(), None):
            for trig in (side, CooldownTrigger.ANY):
                prev = self._last_event.get((scope, trig))
                if prev is None or prev < bar_index:
                    self._last_event[(scope, trig)] = bar_index

    def is_blocked(
        self,
        rules: List[CooldownRule],
        *,
        signal_side: str,
        symbol: str,
        bar_index: int,
    ) -> tuple[bool, Optional[CooldownRule]]:
        for rule in rules or ():
            if rule.bars <= 0:
                continue
            if not rule.applies_to_symbol(symbol):
                continue
            if not rule.blocks_signal(signal_side):
                continue
            scope = None if rule.is_portfolio_scoped else symbol.upper()
            last = self._last_event.get((scope, rule.trigger))
            if last is None:
                continue
            if bar_index - last < rule.bars:
                return True, rule
        return False, None


class TradingCost:
    """A cost model for trading a specific symbol."""

    def __init__(
        self,
        symbol: Optional[str] = None,
        fee_percentage: float = 0.0,
        slippage_percentage: float = 0.0,
        fee_fixed: float = 0.0,
    ):
        self.symbol = symbol.upper() if symbol else None
        self.fee_percentage = fee_percentage
        self.slippage_percentage = slippage_percentage
        self.fee_fixed = fee_fixed

    def get_buy_fill_price(self, price: float, **_) -> float:
        return price * (1 + self.slippage_percentage / 100)

    def get_sell_fill_price(self, price: float, **_) -> float:
        return price * (1 - self.slippage_percentage / 100)

    def get_fee(self, trade_value: float) -> float:
        return trade_value * self.fee_percentage / 100 + self.fee_fixed

    @staticmethod
    def resolve(symbol: str, trading_costs: List["TradingCost"]) -> "TradingCost":
        for tc in trading_costs:
            if tc.symbol and tc.symbol == symbol.upper():
                return tc
        return _ZERO_COST

    def __repr__(self) -> str:
        return (
            f"TradingCost(symbol={self.symbol}, "
            f"fee_percentage={self.fee_percentage}, "
            f"slippage_percentage={self.slippage_percentage})"
        )


_ZERO_COST = TradingCost()
