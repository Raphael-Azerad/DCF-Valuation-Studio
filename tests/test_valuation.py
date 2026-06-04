import pandas as pd
import pytest

from dcf_studio.forecasting import ForecastAssumptions
from dcf_studio.valuation import (
    build_default_scenarios,
    build_sensitivity_matrix,
    probability_weighted_value,
    run_scenarios,
    upside_downside,
    valuation_verdict,
)


def historical_frame():
    return pd.DataFrame(
        {
            "Revenue": [1_000.0, 1_080.0, 1_160.0],
            "EBITDA": [220.0, 243.0, 267.0],
            "Operating Income": [170.0, 188.0, 209.0],
            "Free Cash Flow": [100.0, 119.0, 139.0],
            "Revenue Growth": [None, 0.08, 0.074],
            "EBITDA Margin": [0.22, 0.225, 0.23],
            "Operating Margin": [0.17, 0.174, 0.18],
            "FCF Margin": [0.10, 0.11, 0.12],
        },
        index=[2022, 2023, 2024],
    )


def test_valuation_verdicts_and_upside():
    assert valuation_verdict(120, 100) == "Undervalued"
    assert valuation_verdict(80, 100) == "Overvalued"
    assert valuation_verdict(104, 100) == "Fairly valued"
    assert upside_downside(120, 100) == pytest.approx(0.20)


def test_sensitivity_matrix_outputs_values():
    forecast = pd.DataFrame({"Free Cash Flow": [100.0, 105.0, 110.0]}, index=[2025, 2026, 2027])
    matrix = build_sensitivity_matrix(
        forecast,
        discount_rates=[0.09, 0.10],
        terminal_growth_rates=[0.02, 0.03],
        cash=25.0,
        debt=50.0,
        shares_outstanding=10.0,
    )

    assert matrix.shape == (2, 2)
    assert matrix.loc[0.09, 0.02] > matrix.loc[0.10, 0.02]
    assert matrix.loc[0.09, 0.03] > matrix.loc[0.09, 0.02]


def test_run_scenarios_and_probability_weighted_value():
    base = ForecastAssumptions(
        horizon_years=5,
        near_term_revenue_growth=0.06,
        mature_revenue_growth=0.03,
        target_ebitda_margin=0.24,
        target_operating_margin=0.19,
        target_fcf_margin=0.13,
    )
    scenarios = run_scenarios(
        historical_frame(),
        build_default_scenarios(base, discount_rate=0.09, terminal_growth_rate=0.025),
        cash=100.0,
        debt=200.0,
        shares_outstanding=20.0,
    )

    assert list(scenarios.index) == ["Bear Case", "Base Case", "Bull Case"]
    assert (
        scenarios.loc["Bull Case", "intrinsic_value_per_share"]
        > scenarios.loc["Bear Case", "intrinsic_value_per_share"]
    )
    assert probability_weighted_value(scenarios) > 0


def test_probability_weighted_value_uses_probabilities():
    scenarios = pd.DataFrame(
        {
            "intrinsic_value_per_share": [80.0, 100.0, 140.0],
            "probability": [0.25, 0.50, 0.25],
        }
    )

    assert probability_weighted_value(scenarios) == pytest.approx(105.0)
