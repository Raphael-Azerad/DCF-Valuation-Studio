"""Discounted cash flow valuation engine."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from dcf_studio.exceptions import ValuationInputError


@dataclass(frozen=True)
class DCFInputs:
    """Inputs required for a standard enterprise-value DCF."""

    forecast: pd.DataFrame
    discount_rate: float
    terminal_growth_rate: float
    cash: float
    debt: float
    shares_outstanding: float


@dataclass(frozen=True)
class DCFResult:
    """DCF valuation outputs."""

    forecast_pv: pd.DataFrame
    terminal_value: float
    pv_terminal_value: float
    enterprise_value: float
    equity_value: float
    intrinsic_value_per_share: float
    cash: float
    debt: float
    shares_outstanding: float
    discount_rate: float
    terminal_growth_rate: float

    @property
    def pv_of_forecast_cash_flows(self) -> float:
        return float(self.forecast_pv["PV Free Cash Flow"].sum())


def calculate_dcf(inputs: DCFInputs) -> DCFResult:
    """Calculate enterprise value, equity value, and intrinsic value per share."""
    _validate_inputs(inputs)

    projection = inputs.forecast.copy()
    if "Free Cash Flow" not in projection.columns:
        raise ValuationInputError("Forecast must include a Free Cash Flow column.")

    projection = projection.sort_index()
    periods = range(1, len(projection) + 1)
    projection["Discount Factor"] = [1 / ((1 + inputs.discount_rate) ** period) for period in periods]
    projection["PV Free Cash Flow"] = projection["Free Cash Flow"] * projection["Discount Factor"]

    final_fcf = float(projection["Free Cash Flow"].iloc[-1])
    terminal_value = (
        final_fcf * (1 + inputs.terminal_growth_rate) / (inputs.discount_rate - inputs.terminal_growth_rate)
    )
    pv_terminal_value = terminal_value * float(projection["Discount Factor"].iloc[-1])
    enterprise_value = float(projection["PV Free Cash Flow"].sum() + pv_terminal_value)
    equity_value = enterprise_value - inputs.debt + inputs.cash
    intrinsic_value_per_share = equity_value / inputs.shares_outstanding

    return DCFResult(
        forecast_pv=projection,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal_value,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        intrinsic_value_per_share=intrinsic_value_per_share,
        cash=inputs.cash,
        debt=inputs.debt,
        shares_outstanding=inputs.shares_outstanding,
        discount_rate=inputs.discount_rate,
        terminal_growth_rate=inputs.terminal_growth_rate,
    )


def _validate_inputs(inputs: DCFInputs) -> None:
    if inputs.forecast.empty:
        raise ValuationInputError("Forecast cannot be empty.")
    if inputs.discount_rate <= 0:
        raise ValuationInputError("Discount rate must be positive.")
    if inputs.discount_rate <= inputs.terminal_growth_rate:
        raise ValuationInputError("Discount rate must be greater than terminal growth rate.")
    if inputs.shares_outstanding <= 0:
        raise ValuationInputError("Shares outstanding must be greater than zero.")
    if inputs.cash < 0 or inputs.debt < 0:
        raise ValuationInputError("Cash and debt cannot be negative.")
