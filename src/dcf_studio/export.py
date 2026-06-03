"""Export helpers for model outputs."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from dcf_studio.capm import CAPMResult
from dcf_studio.data import CompanyOverview
from dcf_studio.dcf import DCFResult
from dcf_studio.forecasting import ForecastAssumptions
from dcf_studio.utils import format_currency, format_percent, format_price
from dcf_studio.valuation import upside_downside, valuation_verdict
from dcf_studio.wacc import WACCResult


def build_investment_summary(
    overview: CompanyOverview,
    assumptions: ForecastAssumptions,
    capm: CAPMResult,
    wacc: WACCResult,
    dcf: DCFResult,
) -> str:
    """Generate neutral, README-ready investment summary text."""
    market_price = overview.current_price
    gap = upside_downside(dcf.intrinsic_value_per_share, market_price)
    verdict = valuation_verdict(dcf.intrinsic_value_per_share, market_price)
    return (
        f"{overview.name} ({overview.ticker}) was valued using a {assumptions.horizon_years}-year DCF forecast. "
        f"The model estimates intrinsic value per share of {format_price(dcf.intrinsic_value_per_share)} versus "
        f"a market price of {format_price(market_price)}, implying upside/downside of {format_percent(gap) if gap is not None else 'N/A'}. "
        f"Core assumptions include WACC of {format_percent(wacc.wacc)}, terminal growth of "
        f"{format_percent(dcf.terminal_growth_rate)}, near-term revenue growth of "
        f"{format_percent(assumptions.near_term_revenue_growth)}, and target FCF margin of "
        f"{format_percent(assumptions.target_fcf_margin)}. On these assumptions, the model classifies the shares as "
        f"{verdict.lower()}. This is a valuation exercise, not investment advice."
    )


def export_valuation_workbook(
    *,
    overview: CompanyOverview,
    historical: pd.DataFrame,
    forecast: pd.DataFrame,
    capm: CAPMResult,
    wacc: WACCResult,
    dcf: DCFResult,
    sensitivity: pd.DataFrame,
    scenarios: pd.DataFrame,
) -> bytes:
    """Export the valuation model to an Excel workbook."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([overview.to_dict()]).T.rename(columns={0: "Value"}).to_excel(writer, sheet_name="Overview")
        historical.to_excel(writer, sheet_name="Historical")
        forecast.to_excel(writer, sheet_name="Forecast")
        dcf.forecast_pv.to_excel(writer, sheet_name="DCF Detail")
        sensitivity.to_excel(writer, sheet_name="Sensitivity")
        scenarios.to_excel(writer, sheet_name="Scenarios")
        summary = pd.DataFrame(
            {
                "Metric": [
                    "Market Capitalization",
                    "Enterprise Value",
                    "Equity Value",
                    "Intrinsic Value / Share",
                    "Current Market Price",
                    "Cost of Equity",
                    "WACC",
                    "Terminal Growth",
                ],
                "Value": [
                    format_currency(overview.market_cap),
                    format_currency(dcf.enterprise_value),
                    format_currency(dcf.equity_value),
                    format_price(dcf.intrinsic_value_per_share),
                    format_price(overview.current_price),
                    format_percent(capm.cost_of_equity),
                    format_percent(wacc.wacc),
                    format_percent(dcf.terminal_growth_rate),
                ],
            }
        )
        summary.to_excel(writer, sheet_name="Summary", index=False)

        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            for column_cells in worksheet.columns:
                max_length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 36)

    return output.getvalue()
