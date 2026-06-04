import pandas as pd
import pytest

from dcf_studio.forecasting import ForecastAssumptions, build_forecast, default_forecast_assumptions


def historical_frame():
    return pd.DataFrame(
        {
            "Revenue": [900.0, 1_000.0, 1_100.0],
            "EBITDA": [180.0, 220.0, 253.0],
            "Operating Income": [135.0, 170.0, 198.0],
            "Free Cash Flow": [90.0, 120.0, 143.0],
            "Revenue Growth": [None, 0.1111, 0.10],
            "EBITDA Margin": [0.20, 0.22, 0.23],
            "Operating Margin": [0.15, 0.17, 0.18],
            "FCF Margin": [0.10, 0.12, 0.13],
        },
        index=[2022, 2023, 2024],
    )


def test_build_forecast_projects_revenue_and_fcf():
    result = build_forecast(
        historical_frame(),
        ForecastAssumptions(
            horizon_years=3,
            near_term_revenue_growth=0.10,
            mature_revenue_growth=0.04,
            target_ebitda_margin=0.25,
            target_operating_margin=0.20,
            target_fcf_margin=0.15,
        ),
    )

    assert list(result.forecast.index) == [2025, 2026, 2027]
    assert result.forecast.loc[2025, "Revenue"] == pytest.approx(1_210.0)
    assert result.forecast.loc[2027, "FCF Margin"] == pytest.approx(0.15)
    assert result.forecast.loc[2027, "Free Cash Flow"] > result.forecast.loc[2025, "Free Cash Flow"]


def test_default_assumptions_uses_recent_history():
    assumptions = default_forecast_assumptions(historical_frame())

    assert assumptions.near_term_revenue_growth == pytest.approx(0.10555)
    assert assumptions.target_fcf_margin == pytest.approx(0.13)


def test_default_assumptions_normalizes_distorted_financial_fcf():
    history = pd.DataFrame(
        {
            "Revenue": [100.0, 110.0, 120.0],
            "Net Income": [20.0, 24.0, 30.0],
            "Free Cash Flow": [-70.0, -80.0, -90.0],
            "Revenue Growth": [None, 0.10, 0.091],
            "FCF Margin": [-0.70, -0.727, -0.75],
        },
        index=[2022, 2023, 2024],
    )

    assumptions = default_forecast_assumptions(history)

    assert assumptions.target_fcf_margin == pytest.approx(0.25)
