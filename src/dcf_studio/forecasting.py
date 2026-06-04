"""Financial statement forecasting engine."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dcf_studio.exceptions import ValuationInputError
from dcf_studio.utils import latest_valid, safe_divide, trailing_median


@dataclass(frozen=True)
class ForecastAssumptions:
    """Forecast assumptions for the operating model."""

    horizon_years: int = 5
    near_term_revenue_growth: float = 0.05
    mature_revenue_growth: float = 0.03
    target_ebitda_margin: float | None = None
    target_operating_margin: float | None = None
    target_fcf_margin: float | None = None


@dataclass(frozen=True)
class ForecastResult:
    """Forecast table and the assumptions used to build it."""

    assumptions: ForecastAssumptions
    forecast: pd.DataFrame
    base_year: int


def build_forecast(historical: pd.DataFrame, assumptions: ForecastAssumptions) -> ForecastResult:
    """Build a multi-year forecast from normalized historical financials."""
    if assumptions.horizon_years < 1:
        raise ValuationInputError("Forecast horizon must be at least one year.")
    if "Revenue" not in historical.columns or historical["Revenue"].dropna().empty:
        raise ValuationInputError("Historical revenue is required to build a forecast.")

    clean_history = historical.sort_index().copy()
    latest_revenue = latest_valid(clean_history["Revenue"])
    if latest_revenue is None or latest_revenue <= 0:
        raise ValuationInputError("Latest revenue must be positive.")

    base_year = int(clean_history.index.max())
    starting_margins = _starting_margins(clean_history)
    target_ebitda_margin = _target_margin(assumptions.target_ebitda_margin, starting_margins["EBITDA Margin"])
    target_operating_margin = _target_margin(assumptions.target_operating_margin, starting_margins["Operating Margin"])
    target_fcf_margin = _target_margin(assumptions.target_fcf_margin, starting_margins["FCF Margin"])

    growth_rates = np.linspace(
        assumptions.near_term_revenue_growth,
        assumptions.mature_revenue_growth,
        assumptions.horizon_years,
    )
    ebitda_margins = np.linspace(starting_margins["EBITDA Margin"], target_ebitda_margin, assumptions.horizon_years)
    operating_margins = np.linspace(
        starting_margins["Operating Margin"],
        target_operating_margin,
        assumptions.horizon_years,
    )
    fcf_margins = np.linspace(starting_margins["FCF Margin"], target_fcf_margin, assumptions.horizon_years)

    rows: list[dict[str, float | int]] = []
    revenue = latest_revenue
    for index in range(assumptions.horizon_years):
        year = base_year + index + 1
        revenue *= 1 + growth_rates[index]
        ebitda = revenue * ebitda_margins[index]
        operating_income = revenue * operating_margins[index]
        free_cash_flow = revenue * fcf_margins[index]
        rows.append(
            {
                "Year": year,
                "Revenue Growth": growth_rates[index],
                "Revenue": revenue,
                "EBITDA Margin": ebitda_margins[index],
                "EBITDA": ebitda,
                "Operating Margin": operating_margins[index],
                "Operating Income": operating_income,
                "FCF Margin": fcf_margins[index],
                "Free Cash Flow": free_cash_flow,
            }
        )

    forecast = pd.DataFrame(rows).set_index("Year")
    return ForecastResult(assumptions=assumptions, forecast=forecast, base_year=base_year)


def default_forecast_assumptions(historical: pd.DataFrame, horizon_years: int = 5) -> ForecastAssumptions:
    """Infer balanced default assumptions from historical performance."""
    revenue_growth = trailing_median(historical.get("Revenue Growth", pd.Series(dtype=float)), default=0.05) or 0.05
    revenue_growth = float(np.clip(revenue_growth, -0.05, 0.18))

    margins = _starting_margins(historical)
    return ForecastAssumptions(
        horizon_years=horizon_years,
        near_term_revenue_growth=revenue_growth,
        mature_revenue_growth=min(revenue_growth, 0.035),
        target_ebitda_margin=margins["EBITDA Margin"],
        target_operating_margin=margins["Operating Margin"],
        target_fcf_margin=margins["FCF Margin"],
    )


def _starting_margins(historical: pd.DataFrame) -> dict[str, float]:
    revenue = historical["Revenue"] if "Revenue" in historical else pd.Series(dtype=float)
    defaults = {
        "EBITDA Margin": 0.22,
        "Operating Margin": 0.17,
        "FCF Margin": 0.10,
    }
    margins: dict[str, float] = {}
    for margin_col, numerator_col in (
        ("EBITDA Margin", "EBITDA"),
        ("Operating Margin", "Operating Income"),
        ("FCF Margin", "Free Cash Flow"),
    ):
        margin = latest_valid(historical.get(margin_col, pd.Series(dtype=float)))
        if margin is None and numerator_col in historical and not revenue.empty:
            latest_numerator = latest_valid(historical[numerator_col])
            latest_revenue = latest_valid(revenue)
            margin = safe_divide(latest_numerator, latest_revenue, defaults[margin_col])
        if margin is None:
            margin = trailing_median(historical.get(margin_col, pd.Series(dtype=float)), default=defaults[margin_col])
        margins[margin_col] = float(np.clip(margin or defaults[margin_col], -0.50, 0.75))

    net_income_margin = _net_income_margin(historical)
    if margins["FCF Margin"] < -0.20 and net_income_margin is not None and net_income_margin > 0.05:
        margins["FCF Margin"] = float(np.clip(net_income_margin, 0.02, 0.45))
    return margins


def _target_margin(target: float | None, starting_margin: float) -> float:
    if target is None:
        return starting_margin
    return float(np.clip(target, -0.50, 0.75))


def _net_income_margin(historical: pd.DataFrame) -> float | None:
    if not {"Net Income", "Revenue"}.issubset(historical.columns):
        return None
    net_income = latest_valid(historical["Net Income"])
    revenue = latest_valid(historical["Revenue"])
    if net_income is None or revenue is None or revenue <= 0:
        return None
    return safe_divide(net_income, revenue)
