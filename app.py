from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from dcf_studio.capm import CAPMInputs, calculate_capm
from dcf_studio.data import apply_overrides, fetch_company_data
from dcf_studio.dcf import DCFInputs, calculate_dcf
from dcf_studio.exceptions import DataUnavailableError, ValuationInputError
from dcf_studio.export import build_investment_summary, export_valuation_workbook
from dcf_studio.forecasting import ForecastAssumptions, build_forecast, default_forecast_assumptions
from dcf_studio.utils import format_currency, format_percent, format_price, is_finite
from dcf_studio.valuation import (
    build_default_scenarios,
    build_sensitivity_matrix,
    probability_weighted_value,
    run_scenarios,
    upside_downside,
    valuation_verdict,
)
from dcf_studio.visualization import (
    dcf_cash_flow_chart,
    forecast_chart,
    historical_financials_chart,
    margin_chart,
    revenue_growth_chart,
    scenario_chart,
    sensitivity_heatmap,
    valuation_waterfall,
)
from dcf_studio.wacc import WACCInputs, calculate_wacc

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="DCF Valuation Studio",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_css() -> None:
    css_path = ROOT / "assets" / "dcf-studio.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


@st.cache_data(ttl=60 * 60, show_spinner=False)
def load_dataset(ticker: str):
    return fetch_company_data(ticker)


def as_billions(value: float | None) -> float:
    return float(value / 1_000_000_000) if is_finite(value) else 0.0


def as_millions(value: float | None) -> float:
    return float(value / 1_000_000) if is_finite(value) else 0.0


def pct_input(label: str, value: float, minimum: float, maximum: float, step: float = 0.25) -> float:
    return (
        st.number_input(
            label,
            min_value=minimum * 100,
            max_value=maximum * 100,
            value=float(value * 100),
            step=step,
            format="%.2f",
        )
        / 100
    )


def collect_input_warnings(overview, historical: pd.DataFrame, wacc_value: float, terminal_growth: float) -> list[str]:
    warnings: list[str] = []
    if not is_finite(overview.shares_outstanding) or (overview.shares_outstanding or 0) <= 0:
        warnings.append("Shares outstanding are missing or zero. A per-share valuation cannot be calculated.")
    if overview.cash is None:
        warnings.append("Cash was not available from the data provider. The equity bridge may need a manual override.")
    if overview.debt is None:
        warnings.append("Debt was not available from the data provider. The equity bridge may need a manual override.")
    if "Free Cash Flow" not in historical.columns or historical["Free Cash Flow"].dropna().empty:
        warnings.append("Free cash flow was not available. Review the forecast before relying on the output.")
    if wacc_value <= terminal_growth:
        warnings.append("Terminal growth must be below WACC for the Gordon Growth terminal value formula.")
    elif wacc_value - terminal_growth <= 0.01:
        warnings.append(
            "Terminal growth is within 1.0 percentage point of WACC, making terminal value highly sensitive."
        )
    return warnings


def styled_table(frame: pd.DataFrame) -> pd.io.formats.style.Styler:
    currency_cols = [
        "Revenue",
        "EBITDA",
        "Operating Income",
        "Net Income",
        "Free Cash Flow",
        "PV Free Cash Flow",
        "Enterprise Value",
        "Equity Value",
    ]
    percent_cols = [
        "Revenue Growth",
        "EBITDA Margin",
        "Operating Margin",
        "FCF Margin",
        "Discount Factor",
        "probability",
        "discount_rate",
        "terminal_growth_rate",
        "revenue_growth",
        "fcf_margin",
        "Probability",
        "Discount Rate",
        "Terminal Growth",
        "Revenue Growth",
        "FCF Margin",
    ]
    price_cols = ["intrinsic_value_per_share", "Intrinsic Value / Share"]
    formatters: dict[str, str] = {}
    for column in currency_cols:
        if column in frame.columns:
            formatters[column] = "${:,.0f}"
    for column in percent_cols:
        if column in frame.columns:
            formatters[column] = "{:.1%}"
    for column in price_cols:
        if column in frame.columns:
            formatters[column] = "${:,.2f}"
    return frame.style.format(formatters, na_rep="N/A")


def section_title(title: str, kicker: str | None = None) -> None:
    kicker_html = f"<span>{kicker}</span>" if kicker else ""
    st.markdown(
        f"""
        <div class="section-title">
            {kicker_html}
            <h2>{title}</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, detail: str | None = None, tone: str = "neutral") -> None:
    detail_html = f"<small>{detail}</small>" if detail else ""
    st.markdown(
        f"""
        <div class="metric-card metric-{tone}">
            <span>{label}</span>
            <strong>{value}</strong>
            {detail_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


load_css()

with st.sidebar:
    st.markdown('<div class="sidebar-title">DCF Valuation Studio</div>', unsafe_allow_html=True)
    ticker_choice = st.selectbox("Company ticker", ["AAPL", "LMT", "MSFT", "NVDA", "JPM", "Custom"], index=0)
    ticker = st.text_input("Custom ticker", value="AAPL" if ticker_choice != "Custom" else "").upper()
    if ticker_choice != "Custom":
        ticker = ticker_choice
    run_button = st.button("Run Valuation", width="stretch")

if "active_ticker" not in st.session_state:
    st.session_state.active_ticker = "AAPL"
if run_button or ticker != st.session_state.active_ticker:
    st.session_state.active_ticker = ticker

st.markdown(
    """
    <div class="studio-header">
        <div>
            <span>Financial Modeling Platform</span>
            <h1>DCF Valuation Studio</h1>
        </div>
        <div class="header-mark">CAPM · WACC · DCF · Sensitivity</div>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    with st.spinner(f"Loading {st.session_state.active_ticker} financial data"):
        dataset = load_dataset(st.session_state.active_ticker)
except DataUnavailableError as exc:
    st.error(str(exc))
    st.stop()

raw_overview = dataset.overview
historical = dataset.historical

defaults = default_forecast_assumptions(historical)

with st.sidebar:
    st.divider()
    st.caption("Market data and capital structure")
    current_price = st.number_input(
        "Current market price",
        min_value=0.0,
        value=float(raw_overview.current_price or 0.0),
        step=1.0,
        format="%.2f",
    )
    market_cap = (
        st.number_input(
            "Market capitalization ($B)",
            min_value=0.0,
            value=as_billions(raw_overview.market_cap),
            step=1.0,
            format="%.2f",
        )
        * 1_000_000_000
    )
    shares = (
        st.number_input(
            "Shares outstanding (M)",
            min_value=0.0,
            value=as_millions(raw_overview.shares_outstanding),
            step=10.0,
            format="%.2f",
        )
        * 1_000_000
    )
    cash = (
        st.number_input(
            "Cash and equivalents ($B)",
            min_value=0.0,
            value=as_billions(raw_overview.cash),
            step=1.0,
            format="%.2f",
        )
        * 1_000_000_000
    )
    debt = (
        st.number_input(
            "Total debt ($B)",
            min_value=0.0,
            value=as_billions(raw_overview.debt),
            step=1.0,
            format="%.2f",
        )
        * 1_000_000_000
    )
    beta = st.number_input(
        "Beta",
        min_value=0.0,
        max_value=5.0,
        value=float(raw_overview.beta or 1.0),
        step=0.05,
        format="%.2f",
    )

    st.divider()
    st.caption("Operating forecast")
    horizon_years = st.slider("Forecast horizon", min_value=3, max_value=10, value=int(defaults.horizon_years))
    near_growth = pct_input(
        "Near-term revenue growth (%)",
        defaults.near_term_revenue_growth,
        minimum=-0.20,
        maximum=0.40,
    )
    mature_growth = pct_input(
        "Mature revenue growth (%)",
        defaults.mature_revenue_growth,
        minimum=-0.10,
        maximum=0.15,
    )
    target_ebitda_margin = pct_input(
        "Target EBITDA margin (%)",
        defaults.target_ebitda_margin or 0.20,
        minimum=-0.20,
        maximum=0.75,
    )
    target_operating_margin = pct_input(
        "Target operating margin (%)",
        defaults.target_operating_margin or 0.15,
        minimum=-0.20,
        maximum=0.75,
    )
    target_fcf_margin = pct_input(
        "Target FCF margin (%)",
        defaults.target_fcf_margin or 0.10,
        minimum=-0.30,
        maximum=0.75,
    )

    st.divider()
    st.caption("Cost of capital and terminal value")
    risk_free_rate = pct_input("Risk-free rate (%)", 0.0425, minimum=0.0, maximum=0.15)
    market_risk_premium = pct_input("Market risk premium (%)", 0.055, minimum=0.0, maximum=0.15)
    pre_tax_cost_of_debt = pct_input("Pre-tax cost of debt (%)", 0.048, minimum=0.0, maximum=0.20)
    tax_rate = pct_input("Tax rate (%)", 0.21, minimum=0.0, maximum=0.50)
    terminal_growth_rate = pct_input("Terminal growth rate (%)", 0.025, minimum=-0.02, maximum=0.06)

overview = apply_overrides(
    raw_overview,
    current_price=current_price if current_price else raw_overview.current_price,
    market_cap=market_cap if market_cap else raw_overview.market_cap,
    shares_outstanding=shares if shares else raw_overview.shares_outstanding,
    beta=beta,
    cash=cash,
    debt=debt,
)

forecast_assumptions = ForecastAssumptions(
    horizon_years=horizon_years,
    near_term_revenue_growth=near_growth,
    mature_revenue_growth=mature_growth,
    target_ebitda_margin=target_ebitda_margin,
    target_operating_margin=target_operating_margin,
    target_fcf_margin=target_fcf_margin,
)

try:
    forecast_result = build_forecast(historical, forecast_assumptions)
    capm = calculate_capm(
        CAPMInputs(
            risk_free_rate=risk_free_rate,
            beta=overview.beta or 1.0,
            market_risk_premium=market_risk_premium,
        )
    )
    market_value_equity = overview.market_cap or ((overview.current_price or 0) * (overview.shares_outstanding or 0))
    wacc = calculate_wacc(
        WACCInputs(
            market_value_equity=market_value_equity,
            market_value_debt=overview.debt or 0,
            cost_of_equity=capm.cost_of_equity,
            pre_tax_cost_of_debt=pre_tax_cost_of_debt,
            tax_rate=tax_rate,
        )
    )
    input_warnings = collect_input_warnings(overview, historical, wacc.wacc, terminal_growth_rate)
    dcf = calculate_dcf(
        DCFInputs(
            forecast=forecast_result.forecast,
            discount_rate=wacc.wacc,
            terminal_growth_rate=terminal_growth_rate,
            cash=overview.cash or 0,
            debt=overview.debt or 0,
            shares_outstanding=overview.shares_outstanding or 0,
        )
    )
except ValuationInputError as exc:
    st.error(f"Valuation input issue: {exc}")
    st.stop()

gap = upside_downside(dcf.intrinsic_value_per_share, overview.current_price)
verdict = valuation_verdict(dcf.intrinsic_value_per_share, overview.current_price)
tone = "positive" if verdict == "Undervalued" else "negative" if verdict == "Overvalued" else "neutral"

top_metrics = st.columns(5)
with top_metrics[0]:
    metric_card("Market Price", format_price(overview.current_price), overview.ticker)
with top_metrics[1]:
    metric_card("Intrinsic Value", format_price(dcf.intrinsic_value_per_share), "Base case", tone)
with top_metrics[2]:
    metric_card("Upside / Downside", format_percent(gap), verdict, tone)
with top_metrics[3]:
    metric_card("WACC", format_percent(wacc.wacc), "Discount rate")
with top_metrics[4]:
    metric_card("Enterprise Value", format_currency(dcf.enterprise_value), overview.currency)

for warning in dataset.warnings:
    st.warning(warning)
for warning in input_warnings:
    st.warning(warning)

tabs = st.tabs(
    [
        "Overview",
        "Historical Financials",
        "Forecast Engine",
        "CAPM & WACC",
        "DCF Valuation",
        "Sensitivity",
        "Scenarios",
        "Investment Summary",
    ]
)

with tabs[0]:
    section_title("Company Overview", f"{overview.ticker} · {overview.sector}")
    col_left, col_right = st.columns([1.25, 1])
    with col_left:
        st.markdown(
            f"""
            <div class="company-panel">
                <h3>{overview.name}</h3>
                <p>{overview.summary or "Company summary was not available from the data provider."}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_right:
        overview_table = pd.DataFrame(
            {
                "Metric": [
                    "Industry",
                    "Market Cap",
                    "Current Stock Price",
                    "Enterprise Value",
                    "Shares Outstanding",
                    "Cash",
                    "Debt",
                    "Beta",
                ],
                "Value": [
                    overview.industry,
                    format_currency(overview.market_cap),
                    format_price(overview.current_price),
                    format_currency(overview.enterprise_value),
                    f"{as_millions(overview.shares_outstanding):,.1f}M",
                    format_currency(overview.cash),
                    format_currency(overview.debt),
                    f"{overview.beta:.2f}" if overview.beta else "N/A",
                ],
            }
        )
        st.dataframe(overview_table, hide_index=True, width="stretch")

with tabs[1]:
    section_title("Historical Financials", "Annual statements")
    chart_col, margin_col = st.columns([1.2, 1])
    with chart_col:
        st.plotly_chart(historical_financials_chart(historical))
    with margin_col:
        st.plotly_chart(margin_chart(historical))
    st.plotly_chart(revenue_growth_chart(historical))
    st.dataframe(styled_table(historical), width="stretch")

with tabs[2]:
    section_title("Forecast Engine", f"{forecast_result.base_year + 1}-{forecast_result.base_year + horizon_years}")
    forecast_cols = st.columns(4)
    with forecast_cols[0]:
        metric_card("Near-Term Growth", format_percent(near_growth))
    with forecast_cols[1]:
        metric_card("Mature Growth", format_percent(mature_growth))
    with forecast_cols[2]:
        metric_card("Target FCF Margin", format_percent(target_fcf_margin))
    with forecast_cols[3]:
        metric_card("Forecast Horizon", f"{horizon_years} years")
    st.plotly_chart(forecast_chart(historical, forecast_result.forecast))
    st.dataframe(styled_table(forecast_result.forecast), width="stretch")

with tabs[3]:
    section_title("CAPM & WACC", "Cost of capital")
    capm_col, wacc_col = st.columns(2)
    with capm_col:
        st.markdown(
            f"""
            <div class="formula-panel">
                <span>CAPM</span>
                <h3>{capm.equation}</h3>
                <p>{format_percent(risk_free_rate)} + {overview.beta:.2f} x {format_percent(market_risk_premium)}
                = <strong>{format_percent(capm.cost_of_equity)}</strong></p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Input": ["Risk-Free Rate", "Beta", "Market Risk Premium", "Cost of Equity"],
                    "Value": [
                        format_percent(capm.risk_free_rate),
                        f"{capm.beta:.2f}",
                        format_percent(capm.market_risk_premium),
                        format_percent(capm.cost_of_equity),
                    ],
                }
            ),
            hide_index=True,
            width="stretch",
        )
    with wacc_col:
        st.markdown(
            f"""
            <div class="formula-panel">
                <span>WACC</span>
                <h3>{wacc.equation}</h3>
                <p>Equity weight {format_percent(wacc.equity_weight)} · Debt weight {format_percent(wacc.debt_weight)}
                · After-tax debt cost {format_percent(wacc.after_tax_cost_of_debt)}
                = <strong>{format_percent(wacc.wacc)}</strong></p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Input": ["Market Value Equity", "Market Value Debt", "Tax Rate", "WACC"],
                    "Value": [
                        format_currency(market_value_equity),
                        format_currency(overview.debt),
                        format_percent(wacc.tax_rate),
                        format_percent(wacc.wacc),
                    ],
                }
            ),
            hide_index=True,
            width="stretch",
        )

with tabs[4]:
    section_title("DCF Valuation", "Enterprise to equity value")
    st.caption(
        "Projected free cash flows are discounted at WACC. Terminal value uses Gordon Growth and is then bridged "
        "from enterprise value to equity value by subtracting debt and adding cash."
    )
    valuation_cols = st.columns(5)
    with valuation_cols[0]:
        metric_card("PV Forecast FCF", format_currency(dcf.pv_of_forecast_cash_flows))
    with valuation_cols[1]:
        metric_card("PV Terminal Value", format_currency(dcf.pv_terminal_value))
    with valuation_cols[2]:
        metric_card("Enterprise Value", format_currency(dcf.enterprise_value))
    with valuation_cols[3]:
        metric_card("Equity Value", format_currency(dcf.equity_value))
    with valuation_cols[4]:
        metric_card("Value / Share", format_price(dcf.intrinsic_value_per_share), verdict, tone)
    flow_col, bridge_col = st.columns([1.05, 1])
    with flow_col:
        st.plotly_chart(dcf_cash_flow_chart(dcf))
    with bridge_col:
        st.plotly_chart(valuation_waterfall(dcf))
    st.dataframe(styled_table(dcf.forecast_pv), width="stretch")

with tabs[5]:
    section_title("Sensitivity Analysis", "Intrinsic value per share")
    st.caption("The matrix shows model-implied value per share across WACC and terminal-growth assumptions.")
    discount_rates = np.round(np.linspace(max(wacc.wacc - 0.02, terminal_growth_rate + 0.005), wacc.wacc + 0.02, 7), 4)
    terminal_rates = np.round(np.linspace(terminal_growth_rate - 0.01, terminal_growth_rate + 0.01, 7), 4)
    sensitivity = build_sensitivity_matrix(
        forecast_result.forecast,
        discount_rates,
        terminal_rates,
        cash=overview.cash or 0,
        debt=overview.debt or 0,
        shares_outstanding=overview.shares_outstanding or 0,
    )
    st.plotly_chart(sensitivity_heatmap(sensitivity))
    sensitivity_display = sensitivity.copy()
    sensitivity_display.index = [format_percent(index) for index in sensitivity.index]
    sensitivity_display.columns = [format_percent(column) for column in sensitivity.columns]
    st.dataframe(sensitivity_display.style.format("${:,.2f}", na_rep="N/A"), width="stretch")

with tabs[6]:
    section_title("Scenario Analysis", "Bear · Base · Bull")
    st.caption("Scenarios adjust growth, margins, WACC, and terminal growth around the active base case.")
    scenarios = run_scenarios(
        historical,
        build_default_scenarios(forecast_assumptions, wacc.wacc, terminal_growth_rate),
        cash=overview.cash or 0,
        debt=overview.debt or 0,
        shares_outstanding=overview.shares_outstanding or 0,
    )
    weighted_value = probability_weighted_value(scenarios)
    scenario_cols = st.columns(4)
    with scenario_cols[0]:
        metric_card("Bear Case", format_price(scenarios.loc["Bear Case", "intrinsic_value_per_share"]))
    with scenario_cols[1]:
        metric_card("Base Case", format_price(scenarios.loc["Base Case", "intrinsic_value_per_share"]))
    with scenario_cols[2]:
        metric_card("Bull Case", format_price(scenarios.loc["Bull Case", "intrinsic_value_per_share"]))
    with scenario_cols[3]:
        metric_card("Probability-Weighted", format_price(weighted_value))
    st.plotly_chart(scenario_chart(scenarios, overview.current_price))
    scenario_display = scenarios.rename(
        columns={
            "intrinsic_value_per_share": "Intrinsic Value / Share",
            "enterprise_value": "Enterprise Value",
            "equity_value": "Equity Value",
            "probability": "Probability",
            "discount_rate": "Discount Rate",
            "terminal_growth_rate": "Terminal Growth",
            "revenue_growth": "Revenue Growth",
            "fcf_margin": "FCF Margin",
        }
    )
    st.dataframe(styled_table(scenario_display), width="stretch")

with tabs[7]:
    section_title("Investment Summary", "Neutral model output")
    st.info(
        "This is an educational valuation model based on selected assumptions. It is not investment advice or a price target."
    )
    summary = build_investment_summary(overview, forecast_assumptions, capm, wacc, dcf)
    st.markdown(f'<div class="summary-panel">{summary}</div>', unsafe_allow_html=True)

    st.dataframe(
        pd.DataFrame(
            {
                "Metric": [
                    "Market Price",
                    "Intrinsic Value",
                    "Upside / Downside",
                    "Valuation Conclusion",
                    "WACC",
                    "Terminal Growth",
                    "Forecast Horizon",
                    "Target FCF Margin",
                ],
                "Value": [
                    format_price(overview.current_price),
                    format_price(dcf.intrinsic_value_per_share),
                    format_percent(gap),
                    verdict,
                    format_percent(wacc.wacc),
                    format_percent(terminal_growth_rate),
                    f"{horizon_years} years",
                    format_percent(target_fcf_margin),
                ],
            }
        ),
        hide_index=True,
        width="stretch",
    )

    workbook = export_valuation_workbook(
        overview=overview,
        historical=historical,
        forecast=forecast_result.forecast,
        capm=capm,
        wacc=wacc,
        dcf=dcf,
        sensitivity=sensitivity,
        scenarios=scenarios,
    )
    st.download_button(
        "Export Valuation Workbook",
        data=workbook,
        file_name=f"{overview.ticker}_dcf_valuation.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
