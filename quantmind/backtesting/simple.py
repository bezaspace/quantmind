"""A lightweight single-asset backtest runner for Phase 2 acceptance.

This intentionally mirrors the reference framework's order flow in a
bar-by-bar state machine. It is a stepping-stone to the vector backtest
engine planned for Phase 3.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import polars as pl

from ..domain.models import DataSource, Interval
from ..domain.risk import CooldownRule, PositionSize, ScalingRule, TradingCost
from ..domain.strategy import TradingStrategy
from .result import BacktestResult, max_drawdown

logger = logging.getLogger(__name__)


class SimpleBacktest:
    """Bar-by-bar backtest runner for a single-asset long-only strategy."""

    def __init__(
        self,
        strategy: TradingStrategy,
        data: Dict[str, pl.DataFrame],
        initial_capital: float = 100_000.0,
        start_date: Optional[date | datetime] = None,
        end_date: Optional[date | datetime] = None,
    ):
        self.strategy = strategy
        self.data = data
        self.initial_capital = initial_capital
        self.start_date = start_date
        self.end_date = end_date
        self._symbol = self._resolve_symbol()
        self._key = self._resolve_data_key()

    def _resolve_symbol(self) -> str:
        if not self.strategy.symbols:
            raise ValueError("Strategy has no symbols")
        symbol = self.strategy.symbols[0].upper()
        if len(self.strategy.symbols) > 1:
            logger.warning(
                "SimpleBacktest only supports one symbol; using %s", symbol
            )
        return symbol

    def _resolve_data_key(self) -> str:
        candidates = set(self.data.keys())

        if self.strategy.data_sources:
            ds = self.strategy.data_sources[0]
            if ds.identifier and ds.identifier in candidates:
                return ds.identifier
            if ds.symbol:
                symbol_upper = ds.symbol.upper()
                for key in candidates:
                    if key.upper() == symbol_upper:
                        return key
                for key in candidates:
                    if key.upper().startswith(symbol_upper + "_"):
                        return key
                if symbol_upper in candidates:
                    return symbol_upper

        if self._symbol in candidates:
            return self._symbol
        upper = self._symbol.upper()
        for key in candidates:
            if key.upper() == upper:
                return key
        for key in candidates:
            if key.upper().startswith(upper + "_"):
                return key

        available = list(candidates)
        raise ValueError(
            f"No data found for {self._symbol}. Available keys: {available}"
        )

    def _filter_df(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.sort("Datetime")
        if self.start_date is not None:
            start = self._to_datetime(self.start_date)
            df = df.filter(pl.col("Datetime") >= start)
        if self.end_date is not None:
            end = self._to_datetime(self.end_date, end_of_day=True)
            df = df.filter(pl.col("Datetime") <= end)
        return df

    @staticmethod
    def _to_datetime(
        d: date | datetime, end_of_day: bool = False
    ) -> datetime:
        if isinstance(d, datetime):
            return d
        if end_of_day:
            return datetime.combine(d, datetime.max.time())
        return datetime.combine(d, datetime.min.time())

    def run(self) -> BacktestResult:
        logger.debug("SimpleBacktest.run start for %s", self._symbol)
        df = self._filter_df(self.data[self._key])
        if df.is_empty():
            raise ValueError(f"No data for {self._key} in the requested range")

        prepared = self.strategy.prepare_data({self._key: df})
        buy_signals = self.strategy.generate_buy_signals(prepared)
        sell_signals = self.strategy.generate_sell_signals(prepared)

        def _get_signal_series(signals: Dict[str, pl.Series], default_name: str) -> pl.Series:
            if self._symbol in signals:
                return signals[self._symbol]
            if self._key in signals:
                return signals[self._key]
            return pl.Series(default_name, [False] * len(df))

        buy_series = _get_signal_series(buy_signals, "buy")
        sell_series = _get_signal_series(sell_signals, "sell")

        # Align with the filtered data frame length
        buy_series = buy_series.fill_null(False).cast(pl.Boolean).slice(0, len(df))
        sell_series = sell_series.fill_null(False).cast(pl.Boolean).slice(0, len(df))

        rows = list(df.iter_rows(named=True))

        cash = float(self.initial_capital)
        position_qty = 0.0
        entry_price = 0.0
        high_water_mark = 0.0
        stop_price: Optional[float] = None
        tp_price: Optional[float] = None
        trades: List[Dict[str, Any]] = []
        equity_rows: List[Dict[str, Any]] = []
        cooldown_remaining = 0

        position_size = self._get_position_size()
        stop_rule = self.strategy.get_stop_loss_rule(self._symbol)
        tp_rule = self.strategy.get_take_profit_rule(self._symbol)
        scaling_rule = self.strategy.get_scaling_rule(self._symbol)
        cost = self.strategy.get_trading_cost(self._symbol)
        cooldown_rules = list(self.strategy.cooldowns or [])

        for bar_index, row in enumerate(rows):
            dt = row["Datetime"]
            close = float(row["Close"])
            high = float(row["High"])
            low = float(row["Low"])

            # Update high water mark for trailing stop
            if position_qty > 0:
                if high > high_water_mark:
                    high_water_mark = high
                    if stop_rule and stop_rule.trailing:
                        stop_price = high_water_mark * (
                            1 - stop_rule.percentage_threshold / 100
                        )

            # Check exits first
            exit_triggered = False
            exit_price = close
            exit_reason = "signal"

            if position_qty > 0:
                if stop_rule and stop_price is not None:
                    if low <= stop_price <= high or close <= stop_price:
                        exit_triggered = True
                        exit_price = stop_price
                        exit_reason = "stop_loss"

                if tp_rule and tp_price is not None and not exit_triggered:
                    trigger = close >= tp_price
                    if trigger:
                        exit_triggered = True
                        exit_price = close
                        exit_reason = "take_profit"

                if not exit_triggered and sell_series[bar_index]:
                    exit_triggered = True
                    exit_price = close
                    exit_reason = "sell_signal"

                if exit_triggered:
                    fill_price = cost.get_sell_fill_price(exit_price)
                    gross = position_qty * fill_price
                    fee = cost.get_fee(gross)
                    cash = cash + gross - fee
                    pnl = (fill_price - entry_price) * position_qty - fee
                    trades.append(
                        {
                            "Datetime": dt,
                            "Symbol": self._symbol,
                            "Side": "SELL",
                            "Price": fill_price,
                            "Quantity": position_qty,
                            "Fee": fee,
                            "PnL": pnl,
                            "Reason": exit_reason,
                        }
                    )
                    logger.debug(
                        "bar %s exit %s qty=%s price=%s reason=%s",
                        dt, self._symbol, position_qty, fill_price, exit_reason
                    )
                    position_qty = 0.0
                    entry_price = 0.0
                    high_water_mark = 0.0
                    stop_price = None
                    tp_price = None

            # Decrement cooldown
            if cooldown_remaining > 0:
                cooldown_remaining -= 1

            # Check entry
            if position_qty == 0:
                if cooldown_remaining > 0:
                    continue

                # CooldownRule tracker check
                blocked, _ = self.strategy._cooldown_tracker.is_blocked(
                    cooldown_rules,
                    signal_side="buy",
                    symbol=self._symbol,
                    bar_index=bar_index,
                )
                if blocked:
                    continue

                if buy_series[bar_index]:
                    portfolio_value = cash  # no position yet
                    amount = position_size.get_size(portfolio_value, close)
                    fill_price = cost.get_buy_fill_price(close)
                    qty = amount / fill_price
                    gross = qty * fill_price
                    fee = cost.get_fee(gross)
                    if cash >= gross + fee and qty > 0:
                        cash -= gross + fee
                        position_qty = qty
                        entry_price = fill_price
                        high_water_mark = high
                        if stop_rule and not stop_rule.trailing:
                            stop_price = entry_price * (
                                1 - stop_rule.percentage_threshold / 100
                            )
                        if stop_rule and stop_rule.trailing:
                            stop_price = high_water_mark * (
                                1 - stop_rule.percentage_threshold / 100
                            )
                        if tp_rule:
                            tp_price = entry_price * (
                                1 + tp_rule.percentage_threshold / 100
                            )
                        trades.append(
                            {
                                "Datetime": dt,
                                "Symbol": self._symbol,
                                "Side": "BUY",
                                "Price": fill_price,
                                "Quantity": qty,
                                "Fee": fee,
                                "PnL": -fee,
                                "Reason": "buy_signal",
                            }
                        )
                        logger.debug(
                            "bar %s buy %s qty=%s price=%s",
                            dt, self._symbol, qty, fill_price
                        )

                        if scaling_rule and scaling_rule.cooldown_in_bars:
                            cooldown_remaining = scaling_rule.cooldown_in_bars
                        self.strategy._cooldown_tracker.record(
                            symbol=self._symbol,
                            order_side="buy",
                            bar_index=bar_index,
                        )

            position_value = position_qty * close
            total_equity = cash + position_value
            equity_rows.append(
                {
                    "Datetime": dt,
                    "Cash": cash,
                    "PositionValue": position_value,
                    "TotalEquity": total_equity,
                }
            )

        # Final close at last price if still in position
        if position_qty > 0 and rows:
            last_row = rows[-1]
            last_dt = last_row["Datetime"]
            last_close = float(last_row["Close"])
            fill_price = cost.get_sell_fill_price(last_close)
            gross = position_qty * fill_price
            fee = cost.get_fee(gross)
            cash += gross - fee
            pnl = (fill_price - entry_price) * position_qty - fee
            trades.append(
                {
                    "Datetime": last_dt,
                    "Symbol": self._symbol,
                    "Side": "SELL",
                    "Price": fill_price,
                    "Quantity": position_qty,
                    "Fee": fee,
                    "PnL": pnl,
                    "Reason": "final_close",
                }
            )
            position_qty = 0.0

        if rows:
            last_equity = cash  # no position after final close
        else:
            last_equity = self.initial_capital

        total_return = (last_equity - self.initial_capital) / self.initial_capital

        equity_df = pl.DataFrame(equity_rows)
        max_dd = max_drawdown(equity_df["TotalEquity"]) if not equity_df.is_empty() else 0.0

        trades_df = pl.DataFrame(trades) if trades else pl.DataFrame(
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
        winning_trades = trades_df.filter(
            (pl.col("Side") == "SELL") & (pl.col("PnL") > 0)
        ).height
        win_rate = winning_trades / num_trades if num_trades else 0.0

        logger.debug(
            "SimpleBacktest.run done: total_return=%.4f max_drawdown=%.4f trades=%d",
            total_return, max_dd, num_trades,
        )

        return BacktestResult(
            equity_curve=equity_df,
            trades=trades_df,
            total_return=total_return,
            max_drawdown=max_dd,
            num_trades=num_trades,
            win_rate=win_rate,
            parameters=self.strategy.get_parameters(),
        )

    def _get_position_size(self) -> PositionSize:
        for ps in self.strategy.position_sizes:
            if ps.symbol == self._symbol:
                return ps
        # default: fully invest initial capital
        return PositionSize(symbol=self._symbol, percentage_of_portfolio=100.0)
