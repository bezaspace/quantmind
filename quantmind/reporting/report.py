"""Backtest report with metrics, equity curves, drawdowns, and monthly heatmap."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import polars as pl

from ..backtesting.result import BacktestResult
from ..metrics.core import (
    calculate_metrics,
    drawdown_series,
    monthly_returns_heatmap,
)

logger = logging.getLogger(__name__)


@dataclass
class BacktestReport:
    """A readable, serializable backtest report.

    Contains the full equity curve, trade list, drawdown series, a monthly
    returns heatmap, and a comprehensive metric dictionary. It can export to
    JSON, Markdown, and HTML (with Plotly charts if available).
    """

    name: str
    strategy_id: str
    equity_curve: pl.DataFrame
    trades: pl.DataFrame
    metrics: Dict[str, Any]
    drawdown: pl.Series = field(repr=False)
    monthly_heatmap: pl.DataFrame = field(repr=False)
    risk_free_rate: float = 0.04
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_result(
        cls,
        result: BacktestResult,
        name: Optional[str] = None,
        risk_free_rate: float = 0.04,
        benchmark_returns: Optional[pl.Series] = None,
    ) -> "BacktestReport":
        """Build a report from a ``BacktestResult``."""
        logger.debug("BacktestReport.from_result start")
        name = name or f"backtest-{result.parameters.get('strategy_id', 'unknown')}"
        metrics = calculate_metrics(
            result.equity_curve,
            result.trades,
            risk_free_rate=risk_free_rate,
            benchmark_returns=benchmark_returns,
        )
        dd = drawdown_series(result.equity_curve)
        heatmap = monthly_returns_heatmap(result.equity_curve)
        logger.debug("BacktestReport.from_result done")
        return cls(
            name=name,
            strategy_id=result.parameters.get("strategy_id", "unknown"),
            equity_curve=result.equity_curve,
            trades=result.trades,
            metrics=metrics,
            drawdown=dd,
            monthly_heatmap=heatmap,
            risk_free_rate=risk_free_rate,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary of the report."""
        equity = self.equity_curve.to_dicts()
        trades = self.trades.to_dicts()
        # Convert datetime keys to strings for JSON safety
        metrics = {}
        for k, v in self.metrics.items():
            if v is None:
                metrics[k] = None
            elif isinstance(v, float):
                metrics[k] = round(v, 6)
            elif isinstance(v, int):
                metrics[k] = v
            else:
                metrics[k] = float(v)

        heatmap = self.monthly_heatmap.to_dicts() if not self.monthly_heatmap.is_empty() else []
        drawdown = self.drawdown.to_list()

        return {
            "name": self.name,
            "strategy_id": self.strategy_id,
            "risk_free_rate": self.risk_free_rate,
            "generated_at": self.generated_at.isoformat(),
            "metrics": metrics,
            "equity_curve": equity,
            "trades": trades,
            "drawdown": drawdown,
            "monthly_heatmap": heatmap,
        }

    def to_json(self) -> str:
        """Return the report as a JSON string."""
        data = self.to_dict()
        # JSON cannot serialize native datetime objects
        for row in data["equity_curve"]:
            for key in ("Datetime",):
                if key in row and isinstance(row[key], datetime):
                    row[key] = row[key].isoformat()
        for row in data["trades"]:
            for key in ("Datetime",):
                if key in row and isinstance(row[key], datetime):
                    row[key] = row[key].isoformat()
        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def _df_to_markdown(df: pl.DataFrame, float_fmt: str = ".4f") -> str:
        """Convert a small Polars DataFrame to a Markdown pipe table."""
        if df.is_empty():
            return "_No data._"
        rows = df.to_dicts()
        headers = list(rows[0].keys())
        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        body_lines = []
        for row in rows:
            vals = []
            for h in headers:
                v = row[h]
                if isinstance(v, float):
                    vals.append(f"{v:{float_fmt}}")
                elif isinstance(v, (int,)):
                    vals.append(str(v))
                elif v is None:
                    vals.append("")
                else:
                    vals.append(str(v))
            body_lines.append("| " + " | ".join(vals) + " |")
        return "\n".join([header_line, sep_line] + body_lines)

    def to_markdown(self) -> str:
        """Render a concise Markdown summary of the report."""
        m = self.metrics
        lines = [
            f"# Backtest Report: {self.name}",
            f"**Strategy:** `{self.strategy_id}`  ",
            f"**Generated:** {self.generated_at.isoformat()}  ",
            "",
            "## Key Metrics",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Total Return | {m.get('total_return', 0):.2%} |",
            f"| CAGR | {m.get('cagr', 0):.2%} |",
            f"| Annualized Volatility | {m.get('annualized_volatility', 0):.2%} |",
            f"| Sharpe Ratio | {m.get('sharpe_ratio', 0):.3f} |",
            f"| Sortino Ratio | {m.get('sortino_ratio', 0):.3f} |",
            f"| Max Drawdown | {m.get('max_drawdown', 0):.2%} |",
            f"| Max Drawdown Duration | {m.get('max_drawdown_duration_days', 0)} days |",
            f"| Win Rate | {m.get('win_rate', 0):.2%} |",
            f"| Profit Factor | {m.get('profit_factor', 0):.3f} |",
            f"| Num Trades | {m.get('num_trades', 0)} |",
            f"| Avg Trade Return | {m.get('avg_trade_return', 0):,.2f} |",
            f"| Total Fees | {m.get('total_fees', 0):,.2f} |",
            f"| Exposure | {m.get('exposure', 0):.2%} |",
            "",
            "## Trades",
            "",
        ]
        if self.trades.is_empty():
            lines.append("_No trades._")
        else:
            lines.append(self._df_to_markdown(self.trades.head(20)))
            if self.trades.height > 20:
                lines.append(f"\n_Showing first 20 of {self.trades.height} trades._")
        lines.extend(["", "## Monthly Returns Heatmap", ""])
        if self.monthly_heatmap.is_empty():
            lines.append("_No monthly data._")
        else:
            lines.append(self._df_to_markdown(self.monthly_heatmap, float_fmt=".2%"))
        return "\n".join(lines)

    @staticmethod
    def _df_to_html(df: pl.DataFrame, float_fmt: str = ".4f") -> str:
        """Render a Polars DataFrame as an HTML table without pandas/pyarrow."""
        if df.is_empty():
            return "<p>_No data._</p>"
        rows = df.to_dicts()
        headers = list(rows[0].keys())
        header_html = "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
        body_lines = []
        for row in rows:
            vals = []
            for h in headers:
                v = row[h]
                if isinstance(v, float):
                    vals.append(f"{v:{float_fmt}}")
                elif isinstance(v, (int,)):
                    vals.append(str(v))
                elif v is None:
                    vals.append("")
                else:
                    vals.append(str(v))
            body_lines.append("<tr>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>")
        return f"<table border='1' cellpadding='5' cellspacing='0'><thead>{header_html}</thead><tbody>{''.join(body_lines)}</tbody></table>"

    def _has_plotly(self) -> bool:
        try:
            import plotly.graph_objects as go

            return True
        except ImportError:
            return False

    def _plotly_chart_html(self) -> str:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        dates = self.equity_curve["Datetime"].to_list()
        values = self.equity_curve["TotalEquity"].to_list()
        dds = self.drawdown.to_list()
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3],
            subplot_titles=("Equity Curve", "Drawdown"),
        )
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                mode="lines",
                name="Total Equity",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=dds,
                mode="lines",
                name="Drawdown",
                fill="tozeroy",
            ),
            row=2,
            col=1,
        )
        fig.update_layout(
            title=f"Backtest: {self.name}",
            height=700,
            hovermode="x unified",
            showlegend=False,
        )
        return fig.to_html(full_html=False, include_plotlyjs="cdn")

    def _simple_chart_html(self) -> str:
        """Generate a simple SVG equity/drawdown chart when Plotly is unavailable."""
        values = self.equity_curve["TotalEquity"].to_list()
        dds = self.drawdown.to_list()
        if not values:
            return "<p>No equity data</p>"

        max_eq = max(values) if max(values) != 0 else 1.0
        min_eq = min(values)
        width = 800
        height = 300

        def y_eq(v):
            return height - ((v - min_eq) / (max_eq - min_eq)) * (height - 40) - 20

        points = " ".join(
            f"{i * (width / max(len(values) - 1, 1)):.1f},{y_eq(v):.1f}"
            for i, v in enumerate(values)
        )
        svg = f"""
        <svg viewBox="0 0 {width} {height}" style="width:100%;height:auto;max-width:{width}px;">
            <polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="2"/>
        </svg>
        """
        # Drawdown bar chart
        bar_w = width / max(len(dds), 1)
        bars = ""
        for i, dd in enumerate(dds):
            h = dd * height
            bars += f'<rect x="{i * bar_w}" y="{height - h}" width="{bar_w - 1}" height="{h}" fill="#dc2626" opacity="0.4"/>'
        svg_dd = f"""
        <svg viewBox="0 0 {width} {height}" style="width:100%;height:auto;max-width:{width}px;">
            {bars}
        </svg>
        """
        return f"<div><h3>Equity Curve</h3>{svg}<h3>Drawdown</h3>{svg_dd}</div>"

    def to_html(self, full_page: bool = True) -> str:
        """Render the report as HTML. Uses Plotly if installed, otherwise SVG."""
        chart_html = (
            self._plotly_chart_html()
            if self._has_plotly()
            else self._simple_chart_html()
        )
        metrics_table = "\n".join(
            f"<tr><td>{k}</td><td>{v:.6f}</td></tr>" if isinstance(v, (int, float))
            else f"<tr><td>{k}</td><td>{v}</td></tr>"
            for k, v in self.metrics.items()
        )
        trades_table = ""
        if not self.trades.is_empty():
            trades_table = f"<h2>Trades</h2>\n{self._df_to_html(self.trades)}"
        heatmap_html = ""
        if not self.monthly_heatmap.is_empty():
            heatmap_html = f"<h2>Monthly Returns Heatmap</h2>\n{self._df_to_html(self.monthly_heatmap, float_fmt='.2%')}"

        body = f"""
        <h1>Backtest Report: {self.name}</h1>
        <p><strong>Strategy:</strong> {self.strategy_id}</p>
        <p><strong>Generated:</strong> {self.generated_at.isoformat()}</p>
        {chart_html}
        <h2>Metrics</h2>
        <table border="1" cellpadding="5" cellspacing="0">
            <tr><th>Metric</th><th>Value</th></tr>
            {metrics_table}
        </table>
        {trades_table}
        {heatmap_html}
        """
        if not full_page:
            return body
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Backtest Report: {self.name}</title>
    <style>
        body {{ font-family: sans-serif; margin: 2rem; }}
        table {{ border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ padding: 0.4rem 0.8rem; text-align: left; }}
        th {{ background: #f3f4f6; }}
    </style>
</head>
<body>
{body}
</body>
</html>"""

    def save_html(self, path: str) -> None:
        """Save the HTML report to disk."""
        Path(path).write_text(self.to_html(), encoding="utf-8")

    def save_json(self, path: str) -> None:
        """Save the JSON report to disk."""
        Path(path).write_text(self.to_json(), encoding="utf-8")

    def save_markdown(self, path: str) -> None:
        """Save the Markdown report to disk."""
        Path(path).write_text(self.to_markdown(), encoding="utf-8")
