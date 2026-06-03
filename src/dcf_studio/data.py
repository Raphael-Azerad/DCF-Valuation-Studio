"""Market data and financial statement ingestion."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from dcf_studio.exceptions import DataUnavailableError
from dcf_studio.utils import normalize_ticker, safe_divide, to_float


@dataclass(frozen=True)
class CompanyOverview:
    """A normalized company profile from market data sources."""

    ticker: str
    name: str
    sector: str
    industry: str
    summary: str
    market_cap: float | None
    current_price: float | None
    enterprise_value: float | None
    beta: float | None
    shares_outstanding: float | None
    cash: float | None
    debt: float | None
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FinancialDataset:
    """Company overview plus normalized annual financial history."""

    overview: CompanyOverview
    historical: pd.DataFrame
    warnings: tuple[str, ...] = ()


INCOME_ROWS = {
    "Revenue": ("Total Revenue", "Operating Revenue", "Revenue"),
    "EBITDA": ("EBITDA", "Normalized EBITDA"),
    "Operating Income": ("Operating Income", "Operating Income or Loss"),
    "Net Income": ("Net Income", "Net Income Common Stockholders"),
}

CASH_FLOW_ROWS = {
    "Free Cash Flow": ("Free Cash Flow",),
    "Operating Cash Flow": (
        "Operating Cash Flow",
        "Total Cash From Operating Activities",
        "Net Cash Provided By Operating Activities",
    ),
    "Capital Expenditure": (
        "Capital Expenditure",
        "Capital Expenditures",
        "Capital Expenditure Reported",
    ),
}

BALANCE_ROWS = {
    "Cash": (
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Cash Equivalents And Short Term Investments",
    ),
    "Debt": ("Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt"),
}


def fetch_company_data(ticker: str) -> FinancialDataset:
    """Fetch and normalize company data from yfinance."""
    symbol = normalize_ticker(ticker)
    if not symbol:
        raise DataUnavailableError("Please enter a ticker symbol.")

    try:
        import yfinance as yf
    except ImportError as exc:
        raise DataUnavailableError("yfinance is not installed. Install project requirements first.") from exc

    try:
        yf_ticker = yf.Ticker(symbol)
        info = _safe_info(yf_ticker)
        fast_info = _safe_fast_info(yf_ticker)
        income = _safe_statement(yf_ticker, "income_stmt")
        cash_flow = _safe_statement(yf_ticker, "cashflow")
        balance = _safe_statement(yf_ticker, "balance_sheet")
    except Exception as exc:  # yfinance raises several transport-specific exceptions.
        raise DataUnavailableError(f"Could not load data for {symbol}: {exc}") from exc

    warnings: list[str] = []
    overview = _build_overview(symbol, info, fast_info, balance)
    historical = _build_historical_financials(income, cash_flow, warnings)

    if historical.empty:
        raise DataUnavailableError(
            f"No usable annual financial statements were found for {symbol}. "
            "Try again later or use manual overrides."
        )

    if overview.sector.lower() in {"financial services", "financials"}:
        warnings.append(
            "Financial institutions can have unusual cash-flow and debt profiles; "
            "review FCF, debt, and cash assumptions carefully."
        )

    return FinancialDataset(overview=overview, historical=historical, warnings=tuple(warnings))


def _safe_info(yf_ticker: Any) -> dict[str, Any]:
    try:
        info = yf_ticker.info
    except Exception:
        return {}
    return info if isinstance(info, dict) else {}


def _safe_fast_info(yf_ticker: Any) -> dict[str, Any]:
    try:
        fast_info = yf_ticker.fast_info
    except Exception:
        return {}
    try:
        return dict(fast_info)
    except Exception:
        return {}


def _safe_statement(yf_ticker: Any, attribute: str) -> pd.DataFrame:
    try:
        statement = getattr(yf_ticker, attribute)
    except Exception:
        return pd.DataFrame()
    if statement is None:
        return pd.DataFrame()
    return statement.copy()


def _build_overview(
    ticker: str,
    info: dict[str, Any],
    fast_info: dict[str, Any],
    balance: pd.DataFrame,
) -> CompanyOverview:
    market_cap = _first_float(info, fast_info, "marketCap", "market_cap")
    current_price = _first_float(info, fast_info, "currentPrice", "regularMarketPrice", "last_price")
    shares = _first_float(info, fast_info, "sharesOutstanding", "shares")
    beta = _first_float(info, fast_info, "beta")
    enterprise_value = _first_float(info, fast_info, "enterpriseValue", "enterprise_value")
    cash = _latest_balance_value(balance, BALANCE_ROWS["Cash"])
    debt = _latest_balance_value(balance, BALANCE_ROWS["Debt"])

    if market_cap is None and current_price is not None and shares is not None:
        market_cap = current_price * shares
    if enterprise_value is None and market_cap is not None:
        enterprise_value = market_cap + (debt or 0) - (cash or 0)

    return CompanyOverview(
        ticker=ticker,
        name=str(info.get("longName") or info.get("shortName") or ticker),
        sector=str(info.get("sector") or "Unknown"),
        industry=str(info.get("industry") or "Unknown"),
        summary=str(info.get("longBusinessSummary") or ""),
        market_cap=market_cap,
        current_price=current_price,
        enterprise_value=enterprise_value,
        beta=beta,
        shares_outstanding=shares,
        cash=cash,
        debt=debt,
        currency=str(info.get("financialCurrency") or fast_info.get("currency") or "USD"),
    )


def _build_historical_financials(
    income: pd.DataFrame,
    cash_flow: pd.DataFrame,
    warnings: list[str],
) -> pd.DataFrame:
    metrics: dict[str, pd.Series] = {}

    for metric, candidates in INCOME_ROWS.items():
        series = _select_statement_row(income, candidates)
        if not series.empty:
            metrics[metric] = _series_by_year(series)
        else:
            warnings.append(f"Missing {metric} from income statement.")

    fcf = _select_statement_row(cash_flow, CASH_FLOW_ROWS["Free Cash Flow"])
    if fcf.empty:
        operating_cash_flow = _select_statement_row(cash_flow, CASH_FLOW_ROWS["Operating Cash Flow"])
        capital_expenditure = _select_statement_row(cash_flow, CASH_FLOW_ROWS["Capital Expenditure"])
        if not operating_cash_flow.empty and not capital_expenditure.empty:
            capex_values = capital_expenditure.dropna()
            if not capex_values.empty and capex_values.median() < 0:
                fcf = operating_cash_flow + capital_expenditure
            else:
                fcf = operating_cash_flow - capital_expenditure
            warnings.append("Calculated Free Cash Flow from operating cash flow and capital expenditure.")
        else:
            warnings.append("Missing Free Cash Flow from cash flow statement.")

    if not fcf.empty:
        metrics["Free Cash Flow"] = _series_by_year(fcf)

    if not metrics:
        return pd.DataFrame()

    historical = pd.concat(metrics, axis=1).sort_index()
    historical.index.name = "Year"
    historical = historical.apply(pd.to_numeric, errors="coerce")
    historical = historical.dropna(how="all")

    historical["Revenue Growth"] = historical["Revenue"].pct_change() if "Revenue" in historical else pd.NA
    historical["EBITDA Margin"] = (
        historical["EBITDA"] / historical["Revenue"] if {"EBITDA", "Revenue"}.issubset(historical.columns) else pd.NA
    )
    historical["Operating Margin"] = (
        historical["Operating Income"] / historical["Revenue"]
        if {"Operating Income", "Revenue"}.issubset(historical.columns)
        else pd.NA
    )
    historical["FCF Margin"] = (
        historical["Free Cash Flow"] / historical["Revenue"]
        if {"Free Cash Flow", "Revenue"}.issubset(historical.columns)
        else pd.NA
    )

    return historical


def _select_statement_row(statement: pd.DataFrame, candidates: Iterable[str]) -> pd.Series:
    if statement.empty:
        return pd.Series(dtype=float)

    normalized_index = {_normalize_row_label(index): index for index in statement.index}
    for candidate in candidates:
        if candidate in statement.index:
            return statement.loc[candidate].dropna()
        normalized = _normalize_row_label(candidate)
        if normalized in normalized_index:
            return statement.loc[normalized_index[normalized]].dropna()
    return pd.Series(dtype=float)


def _series_by_year(series: pd.Series) -> pd.Series:
    by_year: dict[int, float] = {}
    for date_like, value in series.items():
        numeric = to_float(value)
        if numeric is None:
            continue
        year = _extract_year(date_like)
        if year is not None:
            by_year[year] = numeric
    return pd.Series(by_year, dtype=float).sort_index()


def _extract_year(value: Any) -> int | None:
    if hasattr(value, "year"):
        return int(value.year)
    try:
        timestamp = pd.Timestamp(value)
    except Exception:
        return None
    if pd.isna(timestamp):
        return None
    return int(timestamp.year)


def _latest_balance_value(balance: pd.DataFrame, candidates: Iterable[str]) -> float | None:
    series = _select_statement_row(balance, candidates)
    if series.empty:
        return None
    yearly = _series_by_year(series)
    if yearly.empty:
        return None
    return to_float(yearly.iloc[-1])


def _first_float(*sources_and_keys: Any) -> float | None:
    sources = [source for source in sources_and_keys if isinstance(source, dict)]
    keys = [key for key in sources_and_keys if isinstance(key, str)]
    for key in keys:
        for source in sources:
            value = to_float(source.get(key))
            if value is not None:
                return value
    return None


def _normalize_row_label(value: Any) -> str:
    return "".join(character.lower() for character in str(value) if character.isalnum())


def apply_overrides(
    overview: CompanyOverview,
    *,
    current_price: float | None = None,
    market_cap: float | None = None,
    shares_outstanding: float | None = None,
    beta: float | None = None,
    cash: float | None = None,
    debt: float | None = None,
) -> CompanyOverview:
    """Return an overview with user-controlled market-data overrides."""
    shares = shares_outstanding if shares_outstanding is not None else overview.shares_outstanding
    price = current_price if current_price is not None else overview.current_price
    cap = market_cap if market_cap is not None else overview.market_cap
    if cap is None and price is not None and shares is not None:
        cap = price * shares

    cash_value = cash if cash is not None else overview.cash
    debt_value = debt if debt is not None else overview.debt
    enterprise_value = cap + (debt_value or 0) - (cash_value or 0) if cap is not None else overview.enterprise_value

    return CompanyOverview(
        ticker=overview.ticker,
        name=overview.name,
        sector=overview.sector,
        industry=overview.industry,
        summary=overview.summary,
        market_cap=cap,
        current_price=price,
        enterprise_value=enterprise_value,
        beta=beta if beta is not None else overview.beta,
        shares_outstanding=shares,
        cash=cash_value,
        debt=debt_value,
        currency=overview.currency,
    )


def enrich_historical_ratios(historical: pd.DataFrame) -> pd.DataFrame:
    """Recalculate derived ratios after a manual historical edit."""
    frame = historical.copy()
    if "Revenue" in frame:
        frame["Revenue Growth"] = frame["Revenue"].pct_change()
    if {"EBITDA", "Revenue"}.issubset(frame.columns):
        frame["EBITDA Margin"] = frame["EBITDA"].combine(frame["Revenue"], safe_divide)
    if {"Operating Income", "Revenue"}.issubset(frame.columns):
        frame["Operating Margin"] = frame["Operating Income"].combine(frame["Revenue"], safe_divide)
    if {"Free Cash Flow", "Revenue"}.issubset(frame.columns):
        frame["FCF Margin"] = frame["Free Cash Flow"].combine(frame["Revenue"], safe_divide)
    return frame
