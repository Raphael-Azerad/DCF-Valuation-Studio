"""DCF Valuation Studio package."""

from dcf_studio.capm import CAPMInputs, CAPMResult, calculate_capm
from dcf_studio.dcf import DCFInputs, DCFResult, calculate_dcf
from dcf_studio.forecasting import ForecastAssumptions, ForecastResult, build_forecast
from dcf_studio.wacc import WACCInputs, WACCResult, calculate_wacc

__all__ = [
    "CAPMInputs",
    "CAPMResult",
    "DCFInputs",
    "DCFResult",
    "ForecastAssumptions",
    "ForecastResult",
    "WACCInputs",
    "WACCResult",
    "build_forecast",
    "calculate_capm",
    "calculate_dcf",
    "calculate_wacc",
]

__version__ = "0.1.0"
