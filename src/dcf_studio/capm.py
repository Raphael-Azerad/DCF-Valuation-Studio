"""Capital Asset Pricing Model calculations."""

from __future__ import annotations

from dataclasses import dataclass

from dcf_studio.exceptions import ValuationInputError


@dataclass(frozen=True)
class CAPMInputs:
    """Inputs for the Capital Asset Pricing Model."""

    risk_free_rate: float
    beta: float
    market_risk_premium: float


@dataclass(frozen=True)
class CAPMResult:
    """Outputs from the Capital Asset Pricing Model."""

    risk_free_rate: float
    beta: float
    market_risk_premium: float
    cost_of_equity: float

    @property
    def equation(self) -> str:
        return "Cost of Equity = Risk-Free Rate + Beta x Market Risk Premium"


def calculate_capm(inputs: CAPMInputs) -> CAPMResult:
    """Calculate cost of equity using CAPM."""
    if inputs.beta < 0:
        raise ValuationInputError("Beta cannot be negative.")
    if inputs.market_risk_premium < 0:
        raise ValuationInputError("Market risk premium cannot be negative.")

    cost_of_equity = inputs.risk_free_rate + (inputs.beta * inputs.market_risk_premium)
    return CAPMResult(
        risk_free_rate=inputs.risk_free_rate,
        beta=inputs.beta,
        market_risk_premium=inputs.market_risk_premium,
        cost_of_equity=cost_of_equity,
    )
