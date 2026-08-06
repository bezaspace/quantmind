"""Event-driven backtest engine with order blotter and cost model."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, Optional

import polars as pl

from ..domain.order import Order, OrderSide, OrderType
from ..domain.strategy import TradingStrategy
from .blotter import ExecutionEngine, Portfolio
from .costs import IndianEquityCostModel
from .result import BacktestResult

logger = logging.getLogger(__name__)


class EventDrivenBacktest:
    """Bar-by-bar event-driven backtester.

    Signals are evaluated for the current bar. New market orders are created
    and placed in the blotter at the close of the signal bar. They are filled
    on the next bar's open so the engine cannot look ahead. Stop/limit orders
    are created immediately and evaluated against subsequent bars.
    """

    def __init__(
        self,
        strategy: TradingStrategy,
        data: Dict[str, pl.DataFrame],
        initial_capital: float = 100_000.0,
        start_date: Optional[date | datetime] = None,
        end_date: Optional[date | datetime] = None,
        cost_model: Optional[IndianEquityCostModel] = None,
        long_only: bool = True,
    ):
        self.strategy = strategy
        self.data = data
        self.initial_capital = initial_capital
        self.start_date = start_date
        self.end_date = end_date
        self.cost_model = cost_model or IndianEquityCostModel()
        self.long_only = long_only
        self.engine = ExecutionEngine(cost_model=self.cost_model, long_only=long_only)
        self.portfolio = Portfolio(cash=initial_capital)

        self._equity_records: list = []
        self._trades: list = []

    def run(self) -> BacktestResult:
        logger.info("EventDrivenBacktest.run start")

        # Normalize datetimes and prepare signals
        prepared = {}
        for key, df in self.data.items():
            df = self._normalize_dt(df)
            if self.start_date:
                df = df.filter(pl.col("Datetime") >= self._to_dt(self.start_date))
            if self.end_date:
                df = df.filter(pl.col("Datetime") <= self._to_dt(self.end_date))
            prepared[key] = df

        prepared = self.strategy.prepare_data(prepared)
        buy_signals = self.strategy.generate_buy_signals(prepared)
        sell_signals = self.strategy.generate_sell_signals(prepared)

        # Build master union index
        all_dates = set()
        for df in prepared.values():
            all_dates.update(df["Datetime"].to_list())
        master = sorted(all_dates)

        # Pre-index per-symbol data and signals
        self._states: Dict[str, Any] = {}
        for key, df in prepared.items():
            sym = self._key_to_symbol(key)
            sig_buy = buy_signals.get(sym, pl.Series([False] * df.height))
            sig_sell = sell_signals.get(sym, pl.Series([False] * df.height))
            df_dict = df.to_dicts()
            row_by_time = {row["Datetime"]: (row, b, s) for row, b, s in zip(df_dict, sig_buy.to_list(), sig_sell.to_list())}
            self._states[key] = {
                "symbol": sym,
                "row_by_time": row_by_time,
                "df_dict": df_dict,
            }

        # Bar loop
        prev_signals: Dict[str, Any] = {}
        for bar_time in master:
            # 1. Process pending orders against current bar
            ohlcv_now = self._snapshot_at(bar_time)
            fills = self.engine.process_bar(bar_time, ohlcv_now)
            for fill in fills:
                pnl = self.engine.apply_fill(fill, self.portfolio)
                self._record_trade(fill, pnl)

            # 2. Evaluate strategy and create new orders
            for key, state in self._states.items():
                row, buy, sell = state["row_by_time"].get(bar_time, (None, False, False))
                if row is None:
                    continue
                sym = state["symbol"]
                pos = self.portfolio.position(sym)
                qty = pos.quantity

                if buy and qty == 0:
                    order = self._create_market_order(sym, OrderSide.BUY, row)
                    if order:
                        self.engine.submit(order)
                elif sell and qty > 0:
                    order = self._create_market_order(sym, OrderSide.SELL, row, quantity=qty)
                    if order:
                        self.engine.submit(order)

            # 3. Record equity
            self._record_equity(bar_time, ohlcv_now)

        return self._build_result()

    def _normalize_dt(self, df: pl.DataFrame) -> pl.DataFrame:
        for col in df.columns:
            if df[col].dtype == pl.Datetime:
                if getattr(df[col].dtype, "time_unit", None) != "us":
                    df = df.with_columns(pl.col(col).cast(pl.Datetime("us")))
        return df

    def _to_dt(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day)
        return datetime.fromisoformat(str(value))

    def _key_to_symbol(self, key: str) -> str:
        # data key is usually "SYMBOL_interval"
        return key.split("_")[0].upper()

    def _snapshot_at(self, bar_time: datetime) -> Dict[str, Dict[str, float]]:
        snapshot = {}
        for key, state in self._states.items():
            entry = state["row_by_time"].get(bar_time)
            if entry:
                snapshot[state["symbol"]] = {
                    "Open": entry[0]["Open"],
                    "High": entry[0]["High"],
                    "Low": entry[0]["Low"],
                    "Close": entry[0]["Close"],
                    "Volume": entry[0]["Volume"],
                }
            else:
                # forward fill last known price for equity valuation
                last = state["df_dict"][-1] if state["df_dict"] else {}
                if last:
                    snapshot[state["symbol"]] = {
                        "Open": last["Close"],
                        "High": last["Close"],
                        "Low": last["Close"],
                        "Close": last["Close"],
                        "Volume": 0.0,
                    }
        return snapshot

    def _create_market_order(
        self,
        symbol: str,
        side: OrderSide,
        row: Dict[str, float],
        quantity: Optional[float] = None,
    ) -> Optional[Order]:
        if quantity is None:
            # Allocate 100% of available cash to this symbol (naive sizing)
            close = float(row["Close"])
            if close <= 0:
                return None
            quantity = self.portfolio.cash / close
        if quantity <= 0:
            return None
        return Order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            price=float(row["Close"]),
            created_at=row.get("Datetime"),
        )

    def _record_trade(self, fill, pnl: float) -> None:
        order = fill.order
        self._trades.append(
            {
                "Datetime": order.filled_at,
                "Symbol": order.symbol,
                "Side": order.side.value,
                "Price": fill.fill_price,
                "Quantity": fill.quantity,
                "Fee": fill.fees,
                "PnL": pnl,
                "Reason": f"{order.order_type.value.lower()}_fill",
            }
        )

    def _record_equity(self, bar_time: datetime, ohlcv: Dict[str, Dict[str, float]]) -> None:
        prices = {sym: float(bar.get("Close", 0.0)) for sym, bar in ohlcv.items()}
        total = self.portfolio.total_value(prices)
        position_value = sum(
            pos.market_value(prices.get(sym, 0.0)) for sym, pos in self.portfolio.positions.items()
        )
        self._equity_records.append(
            {
                "Datetime": bar_time,
                "Cash": self.portfolio.cash,
                "PositionValue": position_value,
                "TotalEquity": total,
            }
        )

    def _build_result(self) -> BacktestResult:
        from ..metrics.core import max_drawdown_metric

        equity_df = pl.DataFrame(self._equity_records)
        trades_df = pl.DataFrame(self._trades) if self._trades else pl.DataFrame(
            schema=[
                ("Datetime", pl.Datetime),
                ("Symbol", pl.Utf8),
                ("Side", pl.Utf8),
                ("Price", pl.Float64),
                ("Quantity", pl.Float64),
                ("Fee", pl.Float64),
                ("PnL", pl.Float64),
                ("Reason", pl.Utf8),
            ]
        )
        if not equity_df.is_empty():
            total_return = float(equity_df["TotalEquity"][-1] / equity_df["TotalEquity"][0] - 1)
        else:
            total_return = 0.0
        max_dd = max_drawdown_metric(equity_df) if not equity_df.is_empty() else 0.0
        sells = trades_df.filter(pl.col("Side") == "SELL")
        num_trades = sells.height
        win_rate = 0.0
        if num_trades > 0:
            win_rate = float((sells["PnL"] > 0).sum() / num_trades)

        return BacktestResult(
            equity_curve=equity_df,
            trades=trades_df,
            total_return=total_return,
            max_drawdown=max_dd,
            num_trades=num_trades,
            win_rate=win_rate,
            parameters=self.strategy.get_parameters(),
        )
