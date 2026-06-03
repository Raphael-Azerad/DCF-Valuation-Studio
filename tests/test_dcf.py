import pandas as pd
import pytest

from dcf_studio.dcf import DCFInputs, calculate_dcf
from dcf_studio.exceptions import ValuationInputError


def forecast_frame():
    return pd.DataFrame(
        {"Free Cash Flow": [100.0, 110.0, 121.0, 133.1, 146.41]},
        index=[2025, 2026, 2027, 2028, 2029],
    )


def test_calculate_dcf_outputs_intrinsic_value():
    result = calculate_dcf(
        DCFInputs(
            forecast=forecast_frame(),
            discount_rate=0.10,
            terminal_growth_rate=0.03,
            cash=50.0,
            debt=150.0,
            shares_outstanding=10.0,
        )
    )

    assert result.terminal_value == pytest.approx(2_154.318571)
    assert result.enterprise_value == pytest.approx(1_792.207792)
    assert result.equity_value == pytest.approx(1_692.207792)
    assert result.intrinsic_value_per_share == pytest.approx(169.220779)


def test_dcf_requires_discount_rate_above_terminal_growth():
    with pytest.raises(ValuationInputError):
        calculate_dcf(
            DCFInputs(
                forecast=forecast_frame(),
                discount_rate=0.03,
                terminal_growth_rate=0.03,
                cash=0.0,
                debt=0.0,
                shares_outstanding=10.0,
            )
        )
