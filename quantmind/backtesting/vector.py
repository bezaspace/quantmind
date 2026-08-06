"""Multi-asset vector backtest runner (bar-by-bar, Polars-aligned).

This is a faster, multi-asset version of the Phase 2 `SimpleBacktest`.
It is still event-driven at the bar level, but signals and prices are
pre-aligned into contiguous arrays so the inner loop is cheap Python.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import polars as pl


from ..domain.risk import (
    CooldownRule,
    CooldownTracker,
    PositionSize,
    ScalingRule,
    StopLossRule,
    TakeProfitRule,
    TradingCost,
)
from ..domain.strategy import TradingStrategy
from .result import BacktestResult, BacktestRun, max_drawdown

logger = logging.getLogger(__name__)


@dataclass
class SymbolState:
    """Runtime state for one symbol during a vector backtest."""

    symbol: str
    key: str
    close: List[float]
    high: List[float]
    low: List[float]
    buy: List[bool]
    sell: List[bool]
    scale_in: List[bool]
    scale_out: List[bool]
    position_size: PositionSize
    trading_cost: TradingCost
    stop_loss: Optional[StopLossRule] = None
    take_profit: Optional[TakeProfitRule] = None
    scaling: Optional[ScalingRule] = None
    qty: float = 0.0
    cost: float = 0.0
    entry_price: float = 0.0
    high_water: float = 0.0
    stop_price: Optional[float] = None
    tp_price: Optional[float] = None
    tp_active: bool = False
    cooldown_remaining: int = 0
    entry_count: int = 0
    scale_out_count: int = 0

    def reset(self) -> None:
        self.qty = 0.0
        self.cost = 0.0
        self.entry_price = 0.0
        self.high_water = 0.0
        self.stop_price = None
        self.tp_price = None
        self.tp_active = False
        self.cooldown_remaining = 0
        self.entry_count = 0
        self.scale_out_count = 0


class VectorBacktest:
    """Bar-by-bar multi-asset backtest runner optimized for vector signals."""

    def __init__(
        self,
        strategy: TradingStrategy,
        data: Dict[str, pl.DataFrame],
        initial_capital: float = 100_000.0,
        start_date: Optional[date | datetime] = None,
        end_date: Optional[date | datetime] = None,
        dynamic_position_sizing: bool = True,
    ):
        self.strategy = strategy
        self.data = data
        self.initial_capital = initial_capital
        self.start_date = start_date
        self.end_date = end_date
        self.dynamic_position_sizing = dynamic_position_sizing
        self.cash = float(initial_capital)
        self.cooldown_tracker = CooldownTracker()

    @staticmethod
    def _to_datetime(d: Optional[date | datetime], end_of_day: bool = False) -> Optional[datetime]:
        if d is None:
            return None
        if isinstance(d, datetime):
            return d
        if end_of_day:
            return datetime.combine(d, datetime.max.time())
        return datetime.combine(d, datetime.min.time())

    def _filter_df(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.sort("Datetime")
        if self.start_date is not None:
            start = self._to_datetime(self.start_date)
            df = df.filter(pl.col("Datetime") >= start)
        if self.end_date is not None:
            end = self._to_datetime(self.end_date, end_of_day=True)
            df = df.filter(pl.col("Datetime") <= end)
        return df

    def _resolve_symbols(self) -> List[str]:
        if self.strategy.symbols:
            return [s.upper() for s in self.strategy.symbols]
        return [k.upper() for k in self.data.keys()]

    def _resolve_key(self, symbol: str) -> str:
        if symbol in self.data:
            return symbol
        for key in self.data:
            if key.upper() == symbol:
                return key
            if key.upper().startswith(symbol + "_"):
                return key
        available = list(self.data.keys())
        raise ValueError(f"No data found for {symbol}. Available: {available}")

    def _build_master_index(self) -> pl.DataFrame:
        dates = set()
        for df in self.data.values():
            df = self._filter_df(df)
            dates.update(df["Datetime"].to_list())
        if not dates:
            raise ValueError("No data in the requested date range")
        master = pl.DataFrame({"Datetime": sorted(dates)})
        return master

    @staticmethod
    def _bool_series_to_list(s: pl.Series, length: int) -> List[bool]:
        if s is None:
            return [False] * length
        s = s.fill_null(False).cast(pl.Boolean)
        return s.to_list()[:length]

    def _prepare_symbol(
        self, symbol: str, master: pl.DataFrame, buy_signals: Dict[str, pl.Series],
        sell_signals: Dict[str, pl.Series], scale_in_signals: Optional[Dict[str, pl.Series]],
        scale_out_signals: Optional[Dict[str, pl.Series]],
    ) -> SymbolState:
        key = self._resolve_key(symbol)
        df = self._filter_df(self.data[key])

        # Identify signal key: prefer symbol, then data key
        sig_key = symbol if symbol in buy_signals else key

        sig_df = pl.DataFrame(
            {
                "Datetime": df["Datetime"],
                "buy": self._bool_series_to_list(
                    buy_signals.get(sig_key), len(df)
                ),
                "sell": self._bool_series_to_list(
                    sell_signals.get(sig_key), len(df)
                ),
                "scale_in": self._bool_series_to_list(
                    scale_in_signals.get(sig_key) if scale_in_signals else None, len(df)
                ),
                "scale_out": self._bool_series_to_list(
                    scale_out_signals.get(sig_key) if scale_out_signals else None, len(df)
                ),
            }
        )

        aligned = (
            master.join(df, on="Datetime", how="left")
            .sort("Datetime")
            .join(sig_df, on="Datetime", how="left")
            .sort("Datetime")
        )

        # Forward- and back-fill price columns; false-fill signals
        aligned = aligned.with_columns(
            [
                pl.col(c).fill_null(strategy="forward").fill_null(strategy="backward")
                for c in ["Open", "High", "Low", "Close", "Volume"]
            ]
        )
        for col in ["buy", "sell", "scale_in", "scale_out"]:
            aligned = aligned.with_columns(pl.col(col).fill_null(False))

        return SymbolState(
            symbol=symbol,
            key=key,
            close=aligned["Close"].to_list(),
            high=aligned["High"].to_list(),
            low=aligned["Low"].to_list(),
            buy=aligned["buy"].to_list(),
            sell=aligned["sell"].to_list(),
            scale_in=aligned["scale_in"].to_list(),
            scale_out=aligned["scale_out"].to_list(),
            position_size=self._position_size_for(symbol),
            trading_cost=TradingCost.resolve(symbol, self.strategy.trading_costs),
            stop_loss=self.strategy.get_stop_loss_rule(symbol),
            take_profit=self.strategy.get_take_profit_rule(symbol),
            scaling=self.strategy.get_scaling_rule(symbol),
        )

    def _position_size_for(self, symbol: str) -> PositionSize:
        for ps in self.strategy.position_sizes:
            if ps.symbol == symbol:
                return ps
        return PositionSize(symbol=symbol, percentage_of_portfolio=100.0)

    def _position_value(self, states: List[SymbolState], bar: int) -> float:
        return sum(s.qty * s.close[bar] for s in states)

    def _portfolio_value(self, states: List[SymbolState], bar: int) -> float:
        return self.cash + self._position_value(states, bar)

    def _execute_buy(self, state: SymbolState, bar: int, dt: datetime, capital: float, reason: str) -> None:
        if capital <= 0:
            return
        price = state.close[bar]
        fill = state.trading_cost.get_buy_fill_price(price)
        fee = state.trading_cost.get_fee(capital)
        net_capital = capital - fee
        if net_capital <= 0:
            return
        qty = net_capital / fill

        self.cash -= capital
        state.entry_price = fill
        state.high_water = state.high[bar]
        state.cost += net_capital
        state.qty += qty
        state.entry_count += 1

        if state.stop_loss:
            if state.stop_loss.trailing:
                state.stop_price = state.high_water * (1 - state.stop_loss.percentage_threshold / 100)
            else:
                state.stop_price = fill * (1 - state.stop_loss.percentage_threshold / 100)

        if state.take_profit:
            state.tp_price = fill * (1 + state.take_profit.percentage_threshold / 100)
            state.tp_active = False

        # Scale-out count resets on a new entry
        state.scale_out_count = 0

        self._trades.append(
            {
                "Datetime": dt,
                "Symbol": state.symbol,
                "Side": "BUY",
                "Price": fill,
                "Quantity": qty,
                "Fee": fee,
                "PnL": -fee,
                "Reason": reason,
            }
        )

        logger.debug("buy %s bar=%s qty=%.4f price=%.2f capital=%.2f reason=%s", state.symbol, dt, qty, fill, capital, reason)

    def _execute_sell(self, state: SymbolState, bar: int, dt: datetime, price: float, reason: str, fraction: float = 1.0) -> None:
        if state.qty <= 0 or fraction <= 0:
            return
        sell_qty = state.qty * fraction
        sell_cost = state.cost * fraction
        fill = state.trading_cost.get_sell_fill_price(price)
        gross = sell_qty * fill
        fee = state.trading_cost.get_fee(gross)
        net = gross - fee
        pnl = net - sell_cost

        self.cash += net
        state.qty -= sell_qty
        state.cost -= sell_cost

        self._trades.append(
            {
                "Datetime": dt,
                "Symbol": state.symbol,
                "Side": "SELL",
                "Price": fill,
                "Quantity": sell_qty,
                "Fee": fee,
                "PnL": pnl,
                "Reason": reason,
            }
        )

        logger.debug("sell %s bar=%s qty=%.4f price=%.2f pnl=%.2f reason=%s", state.symbol, dt, sell_qty, fill, pnl, reason)

        if state.qty <= 1e-12:
            state.qty = 0.0
            state.cost = 0.0
            state.entry_price = 0.0
            state.high_water = 0.0
            state.stop_price = None
            state.tp_price = None
            state.tp_active = False
            state.entry_count = 0
            state.scale_out_count = 0

    def _check_exits(self, state: SymbolState, bar: int) -> Optional[tuple[float, str]]:
        """Return (exit_price, reason) if an exit should occur this bar."""
        close = state.close[bar]
        high = state.high[bar]
        low = state.low[bar]

        # Update trailing-stop high water mark
        if high > state.high_water:
            state.high_water = high
            if state.stop_loss and state.stop_loss.trailing:
                state.stop_price = state.high_water * (1 - state.stop_loss.percentage_threshold / 100)

        # Trailing take profit: activate once price reaches trigger
        if state.take_profit and state.take_profit.trailing and not state.tp_active:
            trigger = state.entry_price * (1 + state.take_profit.percentage_threshold / 100)
            if high >= trigger:
                state.tp_active = True
                state.tp_price = high * (1 - state.take_profit.percentage_threshold / 100)

        if state.tp_active and high > state.tp_price:
            # Trail higher
            state.tp_price = high * (1 - state.take_profit.percentage_threshold / 100)

        if state.stop_loss and state.stop_price is not None:
            if low <= state.stop_price <= high or close <= state.stop_price:
                return min(close, state.stop_price), "stop_loss"

        if state.take_profit and state.tp_price is not None:
            if low <= state.tp_price <= high or close >= state.tp_price:
                return max(close, state.tp_price), "take_profit"

        if state.sell[bar]:
            return close, "sell_signal"

        return None

    def run(self) -> BacktestResult:
        logger.debug("VectorBacktest.run start: strategy=%s", self.strategy.strategy_id)
        self.cash = float(self.initial_capital)
        self.cooldown_tracker.reset()
        self._trades: List[Dict[str, Any]] = []

        # Normalize all Datetime columns to a consistent microsecond precision
        # so provider-specific time units do not break joins.
        for key, df in list(self.data.items()):
            if df.is_empty():
                raise ValueError("One of the provided data frames is empty")
            if df.schema["Datetime"] != pl.Datetime("us"):
                self.data[key] = df.with_columns(
                    pl.col("Datetime").cast(pl.Datetime("us"))
                )

        prepared = self.strategy.prepare_data(self.data)
        for key, df in list(prepared.items()):
            if df.schema["Datetime"] != pl.Datetime("us"):
                prepared[key] = df.with_columns(
                    pl.col("Datetime").cast(pl.Datetime("us"))
                )
        buy_signals = self.strategy.generate_buy_signals(prepared)
        sell_signals = self.strategy.generate_sell_signals(prepared)
        scale_in_signals = self.strategy.generate_scale_in_signals(prepared)
        scale_out_signals = self.strategy.generate_scale_out_signals(prepared)
        if scale_in_signals is None:
            scale_in_signals = buy_signals

        master = self._build_master_index()
        master_dates = master["Datetime"].to_list()
        symbols = self._resolve_symbols()
        states = [
            self._prepare_symbol(
                s,
                master,
                buy_signals,
                sell_signals,
                scale_in_signals,
                scale_out_signals,
            )
            for s in symbols
        ]

        equity_rows: List[Dict[str, Any]] = []

        for bar_index, dt in enumerate(master_dates):
            # Process each symbol sequentially
            for state in states:
                # Decrement per-symbol cooldown
                if state.cooldown_remaining > 0:
                    state.cooldown_remaining -= 1

                # Exits take priority (only if we hold a position)
                if state.qty > 0:
                    exit_info = self._check_exits(state, bar_index)
                    if exit_info:
                        exit_price, reason = exit_info
                        self._execute_sell(state, bar_index, dt, exit_price, reason)
                        state.cooldown_remaining = 0
                        if state.scaling:
                            state.cooldown_remaining = state.scaling.cooldown_in_bars
                        self.cooldown_tracker.record(
                            symbol=state.symbol,
                            order_side="sell",
                            bar_index=bar_index,
                        )
                        continue

                # Skip new entries if in per-symbol cooldown
                if state.cooldown_remaining > 0:
                    continue

                # CooldownRule gating
                blocked, _ = self.cooldown_tracker.is_blocked(
                    self.strategy.cooldowns,
                    signal_side="buy",
                    symbol=state.symbol,
                    bar_index=bar_index,
                )
                if blocked:
                    continue

                if state.qty == 0:
                    if state.buy[bar_index]:
                        portfolio_value = self._portfolio_value(states, bar_index)
                        base_capital = state.position_size.get_size(portfolio_value, state.close[bar_index])
                        if not self.dynamic_position_sizing:
                            # Fixed sizing based on initial capital; guard cash
                            base_capital = min(
                                base_capital,
                                self.initial_capital
                                * (state.position_size.percentage_of_portfolio or 100)
                                / 100,
                            )
                        capital = min(base_capital, self.cash)
                        if capital > 0 and self.cash > 0:
                            self._execute_buy(state, bar_index, dt, capital, "buy_signal")
                            if state.scaling:
                                state.cooldown_remaining = state.scaling.cooldown_in_bars
                            self.cooldown_tracker.record(
                                symbol=state.symbol,
                                order_side="buy",
                                bar_index=bar_index,
                            )
                else:
                    # Scale-in
                    if state.scale_in[bar_index] and state.scaling:
                        if state.entry_count < state.scaling.max_entries:
                            pct = state.scaling.get_scale_in_percentage(state.entry_count - 1)
                            portfolio_value = self._portfolio_value(states, bar_index)
                            base = state.position_size.get_size(portfolio_value, state.close[bar_index])
                            capital = min(base * pct / 100, self.cash)

                            # Max position percentage cap
                            if state.scaling.max_position_percentage is not None:
                                current_pct = (state.qty * state.close[bar_index]) / portfolio_value * 100 if portfolio_value else 0
                                headroom = state.scaling.max_position_percentage - current_pct
                                if headroom <= 0:
                                    continue
                                max_add = portfolio_value * headroom / 100
                                capital = min(capital, max_add)

                            if capital > 0:
                                self._execute_buy(state, bar_index, dt, capital, "scale_in")

                    # Scale-out
                    if state.scale_out[bar_index] and state.scaling:
                        pct = state.scaling.get_scale_out_percentage(state.scale_out_count)
                        state.scale_out_count += 1
                        self._execute_sell(state, bar_index, dt, state.close[bar_index], "scale_out", fraction=pct / 100)

            portfolio_value = self._portfolio_value(states, bar_index)
            equity_rows.append(
                {
                    "Datetime": dt,
                    "Cash": self.cash,
                    "PositionValue": portfolio_value - self.cash,
                    "TotalEquity": portfolio_value,
                }
            )

        # Close all positions at the last close
        if master_dates:
            last_dt = master_dates[-1]
            last_bar = len(master_dates) - 1
            for state in states:
                if state.qty > 0:
                    self._execute_sell(state, last_bar, last_dt, state.close[last_bar], "final_close")

        last_equity = self.cash
        total_return = (last_equity - self.initial_capital) / self.initial_capital

        equity_df = pl.DataFrame(equity_rows)
        max_dd = max_drawdown(equity_df["TotalEquity"]) if not equity_df.is_empty() else 0.0

        trades_df = pl.DataFrame(
            self._trades,
            schema={
                "Datetime": pl.Datetime("ns"),
                "Symbol": pl.Utf8,
                "Side": pl.Utf8,
                "Price": pl.Float64,
                "Quantity": pl.Float64,
                "Fee": pl.Float64,
                "PnL": pl.Float64,
                "Reason": pl.Utf8,
            },
        ) if self._trades else pl.DataFrame(
            schema={
                "Datetime": pl.Datetime("ns"),
                "Symbol": pl.Utf8,
                "Side": pl.Utf8,
                "Price": pl.Float64,
                "Quantity": pl.Float64,
                "Fee": pl.Float64,
                "PnL": pl.Float64,
                "Reason": pl.Utf8,
            }
        )

        num_trades = trades_df.filter(pl.col("Side") == "SELL").height
        winning = trades_df.filter((pl.col("Side") == "SELL") & (pl.col("PnL") > 0)).height
        win_rate = winning / num_trades if num_trades else 0.0

        logger.debug(
            "VectorBacktest.run done: total_return=%.4f max_drawdown=%.4f trades=%d",
            total_return, max_dd, num_trades,
        )

        return BacktestRun(
            equity_curve=equity_df,
            trades=trades_df,
            total_return=total_return,
            max_drawdown=max_dd,
            num_trades=num_trades,
            win_rate=win_rate,
            parameters=self.strategy.get_parameters(),
        )
