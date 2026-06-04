"""Plotly visualizations for the Streamlit dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from dcf_studio.dcf import DCFResult
from dcf_studio.utils import format_price

FINANCE_COLORS = {
    "revenue": "#4EA1D3",
    "ebitda": "#7AC7A9",
    "operating": "#F2C14E",
    "fcf": "#F78166",
    "equity": "#8DD3C7",
    "debt": "#D16666",
    "cash": "#6BBF59",
    "market": "#A7B1C2",
    "text": "#E8EDF3",
    "grid": "rgba(138, 151, 173, 0.20)",
}


def apply_finance_layout(fig: go.Figure, title: str | None = None, height: int = 420) -> go.Figure:
    """Apply a consistent finance-dashboard style."""
    fig.update_layout(
        title=title,
        height=height,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={
            "family": "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont",
            "color": FINANCE_COLORS["text"],
        },
        margin={"l": 18, "r": 18, "t": 54 if title else 24, "b": 24},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        xaxis={"gridcolor": FINANCE_COLORS["grid"], "zerolinecolor": FINANCE_COLORS["grid"]},
        yaxis={"gridcolor": FINANCE_COLORS["grid"], "zerolinecolor": FINANCE_COLORS["grid"]},
    )
    return fig


def historical_financials_chart(historical: pd.DataFrame) -> go.Figure:
    """Chart core historical financial statement lines."""
    fig = go.Figure()
    series_config = [
        ("Revenue", FINANCE_COLORS["revenue"]),
        ("EBITDA", FINANCE_COLORS["ebitda"]),
        ("Operating Income", FINANCE_COLORS["operating"]),
        ("Free Cash Flow", FINANCE_COLORS["fcf"]),
    ]
    for column, color in series_config:
        if column in historical:
            fig.add_trace(
                go.Scatter(
                    x=historical.index,
                    y=historical[column],
                    mode="lines+markers",
                    name=column,
                    line={"width": 3, "color": color},
                    marker={"size": 7},
                    hovertemplate="%{x}<br>%{y:$,.0f}<extra>" + column + "</extra>",
                )
            )
    fig.update_yaxes(tickprefix="$", separatethousands=True)
    return apply_finance_layout(fig, "Historical Financials")


def margin_chart(historical: pd.DataFrame) -> go.Figure:
    """Chart historical margin profile."""
    fig = go.Figure()
    for column, color in (
        ("EBITDA Margin", FINANCE_COLORS["ebitda"]),
        ("Operating Margin", FINANCE_COLORS["operating"]),
        ("FCF Margin", FINANCE_COLORS["fcf"]),
    ):
        if column in historical:
            fig.add_trace(
                go.Scatter(
                    x=historical.index,
                    y=historical[column],
                    mode="lines+markers",
                    name=column,
                    line={"width": 3, "color": color},
                    marker={"size": 7},
                    hovertemplate="%{x}<br>%{y:.1%}<extra>" + column + "</extra>",
                )
            )
    fig.update_yaxes(tickformat=".0%")
    return apply_finance_layout(fig, "Margin Profile")


def revenue_growth_chart(historical: pd.DataFrame) -> go.Figure:
    """Chart annual revenue growth."""
    fig = go.Figure()
    if "Revenue Growth" in historical:
        fig.add_trace(
            go.Bar(
                x=historical.index,
                y=historical["Revenue Growth"],
                marker_color=FINANCE_COLORS["revenue"],
                name="Revenue Growth",
                hovertemplate="%{x}<br>%{y:.1%}<extra></extra>",
            )
        )
    fig.update_yaxes(tickformat=".0%")
    return apply_finance_layout(fig, "Revenue Growth")


def forecast_chart(historical: pd.DataFrame, forecast: pd.DataFrame) -> go.Figure:
    """Show historical and projected Revenue / FCF."""
    fig = go.Figure()
    if "Revenue" in historical:
        fig.add_trace(
            go.Scatter(
                x=historical.index,
                y=historical["Revenue"],
                mode="lines+markers",
                name="Historical Revenue",
                line={"color": FINANCE_COLORS["revenue"], "width": 3},
            )
        )
    if "Free Cash Flow" in historical:
        fig.add_trace(
            go.Scatter(
                x=historical.index,
                y=historical["Free Cash Flow"],
                mode="lines+markers",
                name="Historical FCF",
                line={"color": FINANCE_COLORS["fcf"], "width": 3},
            )
        )
    fig.add_trace(
        go.Scatter(
            x=forecast.index,
            y=forecast["Revenue"],
            mode="lines+markers",
            name="Forecast Revenue",
            line={"color": FINANCE_COLORS["revenue"], "width": 3, "dash": "dash"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=forecast.index,
            y=forecast["Free Cash Flow"],
            mode="lines+markers",
            name="Forecast FCF",
            line={"color": FINANCE_COLORS["fcf"], "width": 3, "dash": "dash"},
        )
    )
    fig.update_yaxes(tickprefix="$", separatethousands=True)
    return apply_finance_layout(fig, "Forecast Engine")


def dcf_cash_flow_chart(result: DCFResult) -> go.Figure:
    """Show projected FCF and present value contribution."""
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=result.forecast_pv.index,
            y=result.forecast_pv["Free Cash Flow"],
            name="Free Cash Flow",
            marker_color=FINANCE_COLORS["fcf"],
            hovertemplate="%{x}<br>%{y:$,.0f}<extra>FCF</extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=result.forecast_pv.index,
            y=result.forecast_pv["PV Free Cash Flow"],
            name="PV Free Cash Flow",
            marker_color=FINANCE_COLORS["ebitda"],
            hovertemplate="%{x}<br>%{y:$,.0f}<extra>PV FCF</extra>",
        )
    )
    fig.update_layout(barmode="group")
    fig.update_yaxes(tickprefix="$", separatethousands=True)
    return apply_finance_layout(fig, "Projected Cash Flows")


def sensitivity_heatmap(matrix: pd.DataFrame) -> go.Figure:
    """Render intrinsic-value sensitivity matrix as a heatmap."""

    def formatter(value: float) -> str:
        return format_price(value) if pd.notna(value) else "N/A"

    text = matrix.map(formatter) if hasattr(matrix, "map") else matrix.applymap(formatter)
    fig = go.Figure(
        data=go.Heatmap(
            z=matrix.values,
            x=[f"{col:.1%}" for col in matrix.columns],
            y=[f"{idx:.1%}" for idx in matrix.index],
            text=text.values,
            texttemplate="%{text}",
            colorscale=[
                [0, "#3E1F2B"],
                [0.35, "#8A4B3A"],
                [0.5, "#273241"],
                [0.70, "#1F5C5B"],
                [1, "#4BAF8C"],
            ],
            colorbar={"title": "Intrinsic Value"},
            hovertemplate="Discount Rate: %{y}<br>Terminal Growth: %{x}<br>Value: %{text}<extra></extra>",
        )
    )
    fig.update_xaxes(title="Terminal Growth Rate")
    fig.update_yaxes(title="Discount Rate")
    return apply_finance_layout(fig, "Sensitivity Analysis", height=500)


def scenario_chart(scenarios: pd.DataFrame, market_price: float | None = None) -> go.Figure:
    """Compare Bear/Base/Bull intrinsic values per share."""
    fig = go.Figure()
    colors = ["#D16666", "#F2C14E", "#4BAF8C"]
    fig.add_trace(
        go.Bar(
            x=scenarios.index,
            y=scenarios["intrinsic_value_per_share"],
            marker_color=colors[: len(scenarios)],
            name="Intrinsic Value",
            hovertemplate="%{x}<br>%{y:$,.2f}<extra></extra>",
        )
    )
    if market_price and market_price > 0:
        fig.add_hline(
            y=market_price,
            line_dash="dash",
            line_color=FINANCE_COLORS["market"],
            annotation_text=f"Market Price {format_price(market_price)}",
            annotation_position="top right",
        )
    fig.update_yaxes(tickprefix="$")
    return apply_finance_layout(fig, "Scenario Valuation Range")


def valuation_waterfall(result: DCFResult) -> go.Figure:
    """Create enterprise-to-equity valuation bridge."""
    shares = result.shares_outstanding
    enterprise_per_share = result.enterprise_value / shares
    debt_per_share = result.debt / shares
    cash_per_share = result.cash / shares
    equity_per_share = result.equity_value / shares
    fig = go.Figure(
        go.Waterfall(
            name="Valuation Bridge",
            orientation="v",
            measure=["absolute", "relative", "relative", "total", "total"],
            x=[
                "Enterprise Value / Share",
                "Less Debt / Share",
                "Add Cash / Share",
                "Equity Value / Share",
                "Intrinsic Value / Share",
            ],
            y=[
                enterprise_per_share,
                -debt_per_share,
                cash_per_share,
                equity_per_share,
                result.intrinsic_value_per_share,
            ],
            connector={"line": {"color": FINANCE_COLORS["grid"]}},
            increasing={"marker": {"color": FINANCE_COLORS["cash"]}},
            decreasing={"marker": {"color": FINANCE_COLORS["debt"]}},
            totals={"marker": {"color": FINANCE_COLORS["equity"]}},
            hovertemplate="%{x}<br>%{y:$,.2f}<extra></extra>",
        )
    )
    fig.update_yaxes(tickprefix="$", separatethousands=True)
    return apply_finance_layout(fig, "Valuation Waterfall")
