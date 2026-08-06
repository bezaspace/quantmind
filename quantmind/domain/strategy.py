"""Trading strategy abstraction, adapted from proven framework patterns."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import polars as pl

from .exceptions import ConfigurationError, QuantMindError, StrategyError
from .models import DataSource, DataType, Interval, TimeUnit
from .risk import (
    CooldownRule,
    CooldownTracker,
    PositionSize,
    ScalingRule,
    StopLossRule,
    TakeProfitRule,
    TradingCost,
)

logger = logging.getLogger(__name__)


class TradingStrategy:
    """Base class for all trading strategies.

    Subclasses declare class attributes and override at least one of
    :meth:`generate_buy_signals` and :meth:`generate_sell_signals`.
    """

    algorithm_id: Optional[str] = None
    strategy_id: Optional[str] = None
    time_unit: TimeUnit = TimeUnit.DAY
    interval: int = 1
    market: str = "NSE"
    product_type: str = "CNC"
    long_only: bool = True
    symbols: List[str] = []
    data_sources: List[DataSource] = []
    position_sizes: List[PositionSize] = []
    stop_losses: List[StopLossRule] = []
    take_profits: List[TakeProfitRule] = []
    scaling_rules: List[ScalingRule] = []
    cooldowns: List[CooldownRule] = []
    trading_costs: List[TradingCost] = []
    metadata: Dict[str, Any] = {}

    def __init__(
        self,
        algorithm_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        time_unit: Optional[TimeUnit | str] = None,
        interval: Optional[int] = None,
        market: Optional[str] = None,
        product_type: Optional[str] = None,
        long_only: Optional[bool] = None,
        symbols: Optional[List[str]] = None,
        data_sources: Optional[List[DataSource]] = None,
        position_sizes: Optional[List[PositionSize]] = None,
        stop_losses: Optional[List[StopLossRule]] = None,
        take_profits: Optional[List[TakeProfitRule]] = None,
        scaling_rules: Optional[List[ScalingRule]] = None,
        cooldowns: Optional[List[CooldownRule]] = None,
        trading_costs: Optional[List[TradingCost]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        logger.debug("TradingStrategy __init__ start")

        self.metadata = dict(metadata if metadata is not None else self.__class__.metadata or {})

        self.strategy_id = strategy_id or self.__class__.strategy_id or self.__class__.__name__
        self.algorithm_id = algorithm_id or self.__class__.algorithm_id

        if time_unit is not None:
            self.time_unit = TimeUnit.from_value(time_unit) if isinstance(time_unit, str) else time_unit
        else:
            self.time_unit = self.__class__.time_unit
            if self.time_unit is None:
                raise ConfigurationError("time_unit is required")
            if isinstance(self.time_unit, str):
                self.time_unit = TimeUnit.from_value(self.time_unit)

        self.interval = interval if interval is not None else self.__class__.interval
        if self.interval is None:
            raise ConfigurationError("interval is required")

        self.market = (market or self.__class__.market or "NSE").upper()
        self.product_type = (product_type or self.__class__.product_type or "CNC").upper()
        self.long_only = long_only if long_only is not None else self.__class__.long_only

        self.symbols = list(symbols if symbols is not None else self.__class__.symbols)
        self.data_sources = list(data_sources if data_sources is not None else self.__class__.data_sources)
        self.position_sizes = list(position_sizes if position_sizes is not None else self.__class__.position_sizes)
        self.stop_losses = list(stop_losses if stop_losses is not None else self.__class__.stop_losses)
        self.take_profits = list(take_profits if take_profits is not None else self.__class__.take_profits)
        self.scaling_rules = list(scaling_rules if scaling_rules is not None else self.__class__.scaling_rules)
        self.cooldowns = list(cooldowns if cooldowns is not None else self.__class__.cooldowns)
        self.trading_costs = list(trading_costs if trading_costs is not None else self.__class__.trading_costs)

        self._parameters: Dict[str, Any] = {}
        self._cooldown_tracker = CooldownTracker()
        self._cooldown_remaining: Dict[str, int] = {}
        self._cooldown_bar_index = 0

        self._validate_data_sources()
        logger.debug("TradingStrategy __init__ done")

    def _validate_data_sources(self) -> None:
        """Ensure the strategy scheduling interval is not faster than data."""
        ohlcv_minutes = [
            ds.interval.amount_of_minutes
            for ds in self.data_sources
            if ds.data_type == DataType.OHLCV and ds.interval is not None
        ]
        if not ohlcv_minutes:
            return

        scheduling_minutes = self.time_unit.amount_of_minutes * self.interval
        smallest_timeframe = min(ohlcv_minutes)
        if scheduling_minutes < smallest_timeframe:
            raise StrategyError(
                f"Strategy '{self.strategy_id}' scheduling interval "
                f"({self.interval} {self.time_unit.value} = {scheduling_minutes} min) "
                f"is faster than the smallest OHLCV data source timeframe "
                f"({smallest_timeframe} min)."
            )

        for ds in self.data_sources:
            if ds.symbol and ds.symbol.upper() not in {s.upper() for s in self.symbols}:
                logger.debug(
                    "data source symbol %s not in strategy symbols %s",
                    ds.symbol, self.symbols
                )

    def set_parameters(self, params: Dict[str, Any]) -> None:
        """Store JSON-serializable strategy parameters."""
        json_types = (str, int, float, bool, type(None))

        def _is_serializable(value: Any) -> bool:
            if isinstance(value, json_types):
                return True
            if isinstance(value, (list, tuple)):
                return all(_is_serializable(x) for x in value)
            if isinstance(value, dict):
                return all(
                    isinstance(k, str) and _is_serializable(v)
                    for k, v in value.items()
                )
            return False

        self._parameters = {
            k: v for k, v in params.items() if _is_serializable(v)
        }

    def get_parameters(self) -> Dict[str, Any]:
        """Return stored strategy parameters."""
        return dict(self._parameters)

    def generate_buy_signals(
        self, data: Dict[str, pl.DataFrame]
    ) -> Dict[str, pl.Series]:
        """Return a dict of {symbol: boolean polars Series} buy signals."""
        raise NotImplementedError(
            "generate_buy_signals must be implemented by the strategy"
        )

    def generate_sell_signals(
        self, data: Dict[str, pl.DataFrame]
    ) -> Dict[str, pl.Series]:
        """Return a dict of {symbol: boolean polars Series} sell signals."""
        raise NotImplementedError(
            "generate_sell_signals must be implemented by the strategy"
        )

    def generate_scale_in_signals(
        self, data: Dict[str, pl.DataFrame]
    ) -> Optional[Dict[str, pl.Series]]:
        """Optional scale-in signals. Defaults to buy signals."""
        return None

    def generate_scale_out_signals(
        self, data: Dict[str, pl.DataFrame]
    ) -> Optional[Dict[str, pl.Series]]:
        """Optional scale-out signals. Defaults to no scale-out."""
        return None

    def prepare_data(self, data: Dict[str, pl.DataFrame]) -> Dict[str, pl.DataFrame]:
        """Optional hook to pre-compute indicators on each data frame."""
        return data

    def get_position_size(self, symbol: str) -> PositionSize:
        symbol = symbol.upper()
        for ps in self.position_sizes:
            if ps.symbol == symbol:
                return ps
        raise StrategyError(f"No PositionSize defined for {symbol}")

    def get_stop_loss_rule(self, symbol: str) -> Optional[StopLossRule]:
        symbol = symbol.upper()
        for rule in self.stop_losses:
            if rule.symbol == symbol:
                return rule
        return None

    def get_take_profit_rule(self, symbol: str) -> Optional[TakeProfitRule]:
        symbol = symbol.upper()
        for rule in self.take_profits:
            if rule.symbol == symbol:
                return rule
        return None

    def get_scaling_rule(self, symbol: str) -> Optional[ScalingRule]:
        symbol = symbol.upper()
        for rule in self.scaling_rules:
            if rule.symbol == symbol:
                return rule
        return None

    def get_trading_cost(self, symbol: str) -> TradingCost:
        return TradingCost.resolve(symbol, self.trading_costs)

    def reset_state(self) -> None:
        """Reset runtime state between backtest runs."""
        self._cooldown_tracker.reset()
        self._cooldown_remaining.clear()
        self._cooldown_bar_index = 0

    def __repr__(self) -> str:
        return (
            f"TradingStrategy(algorithm_id={self.algorithm_id}, "
            f"strategy_id={self.strategy_id}, market={self.market}, "
            f"symbols={self.symbols})"
        )
