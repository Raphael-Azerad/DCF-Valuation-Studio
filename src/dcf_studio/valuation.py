"""Scenario, sensitivity, and valuation summary helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from dcf_studio.dcf import DCFInputs, DCFResult, calculate_dcf
from dcf_studio.exceptions import ValuationInputError
from dcf_studio.forecasting import ForecastAssumptions, ForecastResult, build_forecast


@dataclass(frozen=True)
class ScenarioAssumptions:
    """A complete scenario for valuation comparison."""

    name: str
    forecast_assumptions: ForecastAssumptions
    discount_rate: float
    terminal_growth_rate: float
    probability: float


@dataclass(frozen=True)
class ScenarioResult:
    """Scenario output for valuation range charts."""

    name: str
    intrinsic_value_per_share: float
    enterprise_value: float
    equity_value: float
    probability: float
    discount_rate: float
    terminal_growth_rate: float
    revenue_growth: float
    fcf_margin: float | None


def valuation_verdict(
    intrinsic_value_per_share: float,
    market_price: float | None,
    fair_value_band: float = 0.10,
) -> str:
    """Classify the gap between model value and market price."""
    if market_price is None or market_price <= 0:
        return "Market price unavailable"
    gap = (intrinsic_value_per_share - market_price) / market_price
    if gap > fair_value_band:
        return "Undervalued"
    if gap < -fair_value_band:
        return "Overvalued"
    return "Fairly valued"


def upside_downside(intrinsic_value_per_share: float, market_price: float | None) -> float | None:
    """Calculate upside/downside as a decimal."""
    if market_price is None or market_price <= 0:
        return None
    return (intrinsic_value_per_share / market_price) - 1


def build_sensitivity_matrix(
    forecast: pd.DataFrame,
    discount_rates: Iterable[float],
    terminal_growth_rates: Iterable[float],
    *,
    cash: float,
    debt: float,
    shares_outstanding: float,
) -> pd.DataFrame:
    """Build an investment-banking-style intrinsic value sensitivity matrix."""
    rows: dict[float, dict[float, float]] = {}
    for discount_rate in discount_rates:
        row: dict[float, float] = {}
        for terminal_growth_rate in terminal_growth_rates:
            if discount_rate <= terminal_growth_rate:
                row[terminal_growth_rate] = np.nan
                continue
            try:
                result = calculate_dcf(
                    DCFInputs(
                        forecast=forecast,
                        discount_rate=discount_rate,
                        terminal_growth_rate=terminal_growth_rate,
                        cash=cash,
                        debt=debt,
                        shares_outstanding=shares_outstanding,
                    )
                )
            except ValuationInputError:
                row[terminal_growth_rate] = np.nan
            else:
                row[terminal_growth_rate] = result.intrinsic_value_per_share
        rows[discount_rate] = row
    matrix = pd.DataFrame.from_dict(rows, orient="index")
    matrix.index.name = "Discount Rate"
    matrix.columns.name = "Terminal Growth"
    return matrix


def build_default_scenarios(
    base: ForecastAssumptions, discount_rate: float, terminal_growth_rate: float
) -> list[ScenarioAssumptions]:
    """Create Bear/Base/Bull cases around the active model assumptions."""
    base_fcf_margin = base.target_fcf_margin if base.target_fcf_margin is not None else 0.10
    base_ebitda_margin = base.target_ebitda_margin if base.target_ebitda_margin is not None else 0.20
    base_operating_margin = base.target_operating_margin if base.target_operating_margin is not None else 0.16

    return [
        ScenarioAssumptions(
            name="Bear Case",
            forecast_assumptions=ForecastAssumptions(
                horizon_years=base.horizon_years,
                near_term_revenue_growth=base.near_term_revenue_growth - 0.025,
                mature_revenue_growth=max(base.mature_revenue_growth - 0.010, -0.010),
                target_ebitda_margin=base_ebitda_margin - 0.020,
                target_operating_margin=base_operating_margin - 0.020,
                target_fcf_margin=base_fcf_margin - 0.020,
            ),
            discount_rate=discount_rate + 0.015,
            terminal_growth_rate=max(terminal_growth_rate - 0.005, -0.010),
            probability=0.25,
        ),
        ScenarioAssumptions(
            name="Base Case",
            forecast_assumptions=base,
            discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate,
            probability=0.50,
        ),
        ScenarioAssumptions(
            name="Bull Case",
            forecast_assumptions=ForecastAssumptions(
                horizon_years=base.horizon_years,
                near_term_revenue_growth=base.near_term_revenue_growth + 0.025,
                mature_revenue_growth=base.mature_revenue_growth + 0.010,
                target_ebitda_margin=base_ebitda_margin + 0.020,
                target_operating_margin=base_operating_margin + 0.020,
                target_fcf_margin=base_fcf_margin + 0.020,
            ),
            discount_rate=max(discount_rate - 0.010, terminal_growth_rate + 0.010),
            terminal_growth_rate=terminal_growth_rate + 0.005,
            probability=0.25,
        ),
    ]


def run_scenarios(
    historical: pd.DataFrame,
    scenarios: Iterable[ScenarioAssumptions],
    *,
    cash: float,
    debt: float,
    shares_outstanding: float,
) -> pd.DataFrame:
    """Run scenario valuations and return a comparison table."""
    rows: list[ScenarioResult] = []
    for scenario in scenarios:
        forecast: ForecastResult = build_forecast(historical, scenario.forecast_assumptions)
        dcf: DCFResult = calculate_dcf(
            DCFInputs(
                forecast=forecast.forecast,
                discount_rate=scenario.discount_rate,
                terminal_growth_rate=scenario.terminal_growth_rate,
                cash=cash,
                debt=debt,
                shares_outstanding=shares_outstanding,
            )
        )
        rows.append(
            ScenarioResult(
                name=scenario.name,
                intrinsic_value_per_share=dcf.intrinsic_value_per_share,
                enterprise_value=dcf.enterprise_value,
                equity_value=dcf.equity_value,
                probability=scenario.probability,
                discount_rate=scenario.discount_rate,
                terminal_growth_rate=scenario.terminal_growth_rate,
                revenue_growth=scenario.forecast_assumptions.near_term_revenue_growth,
                fcf_margin=scenario.forecast_assumptions.target_fcf_margin,
            )
        )
    return pd.DataFrame([row.__dict__ for row in rows]).set_index("name")


def probability_weighted_value(scenarios: pd.DataFrame) -> float:
    """Calculate probability-weighted intrinsic value per share."""
    if scenarios.empty:
        return float("nan")
    probabilities = scenarios["probability"]
    total_probability = probabilities.sum()
    if total_probability <= 0:
        return float("nan")
    return float((scenarios["intrinsic_value_per_share"] * probabilities).sum() / total_probability)
