"""Weighted Average Cost of Capital calculations."""

from __future__ import annotations

from dataclasses import dataclass

from dcf_studio.exceptions import ValuationInputError


@dataclass(frozen=True)
class WACCInputs:
    """Inputs for the Weighted Average Cost of Capital."""

    market_value_equity: float
    market_value_debt: float
    cost_of_equity: float
    pre_tax_cost_of_debt: float
    tax_rate: float


@dataclass(frozen=True)
class WACCResult:
    """Outputs from the Weighted Average Cost of Capital."""

    equity_weight: float
    debt_weight: float
    cost_of_equity: float
    after_tax_cost_of_debt: float
    tax_rate: float
    wacc: float

    @property
    def equation(self) -> str:
        return "WACC = (E / V x Re) + (D / V x Rd x (1 - Tax Rate))"


def calculate_wacc(inputs: WACCInputs) -> WACCResult:
    """Calculate WACC from market capital structure and financing costs."""
    if inputs.market_value_equity < 0 or inputs.market_value_debt < 0:
        raise ValuationInputError("Debt and equity values cannot be negative.")
    if inputs.market_value_equity + inputs.market_value_debt <= 0:
        raise ValuationInputError("Total capital must be greater than zero.")
    if inputs.tax_rate < 0 or inputs.tax_rate > 1:
        raise ValuationInputError("Tax rate must be between 0% and 100%.")
    if inputs.cost_of_equity < 0 or inputs.pre_tax_cost_of_debt < 0:
        raise ValuationInputError("Costs of capital cannot be negative.")

    total_capital = inputs.market_value_equity + inputs.market_value_debt
    equity_weight = inputs.market_value_equity / total_capital
    debt_weight = inputs.market_value_debt / total_capital
    after_tax_cost_of_debt = inputs.pre_tax_cost_of_debt * (1 - inputs.tax_rate)
    wacc = (equity_weight * inputs.cost_of_equity) + (debt_weight * after_tax_cost_of_debt)

    return WACCResult(
        equity_weight=equity_weight,
        debt_weight=debt_weight,
        cost_of_equity=inputs.cost_of_equity,
        after_tax_cost_of_debt=after_tax_cost_of_debt,
        tax_rate=inputs.tax_rate,
        wacc=wacc,
    )
