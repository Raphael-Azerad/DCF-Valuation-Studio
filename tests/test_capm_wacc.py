import pytest

from dcf_studio.capm import CAPMInputs, calculate_capm
from dcf_studio.exceptions import ValuationInputError
from dcf_studio.wacc import WACCInputs, calculate_wacc


def test_calculate_capm_cost_of_equity():
    result = calculate_capm(CAPMInputs(risk_free_rate=0.04, beta=1.2, market_risk_premium=0.055))

    assert result.cost_of_equity == pytest.approx(0.106)


def test_capm_rejects_negative_beta():
    with pytest.raises(ValuationInputError):
        calculate_capm(CAPMInputs(risk_free_rate=0.04, beta=-0.5, market_risk_premium=0.055))


def test_calculate_wacc_blends_equity_and_after_tax_debt():
    result = calculate_wacc(
        WACCInputs(
            market_value_equity=800,
            market_value_debt=200,
            cost_of_equity=0.10,
            pre_tax_cost_of_debt=0.05,
            tax_rate=0.21,
        )
    )

    expected = (0.8 * 0.10) + (0.2 * 0.05 * (1 - 0.21))
    assert result.wacc == pytest.approx(expected)
    assert result.equity_weight == pytest.approx(0.8)
    assert result.debt_weight == pytest.approx(0.2)


def test_wacc_rejects_invalid_capital_structure():
    with pytest.raises(ValuationInputError):
        calculate_wacc(
            WACCInputs(
                market_value_equity=0,
                market_value_debt=0,
                cost_of_equity=0.10,
                pre_tax_cost_of_debt=0.05,
                tax_rate=0.21,
            )
        )
