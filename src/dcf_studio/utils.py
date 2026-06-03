"""Shared formatting and validation utilities."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def normalize_ticker(ticker: str) -> str:
    """Return a clean uppercase ticker symbol."""
    return ticker.strip().upper().replace(" ", "")


def is_finite(value: Any) -> bool:
    """Return True for finite numeric values."""
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def to_float(value: Any, default: float | None = None) -> float | None:
    """Coerce common finance-library outputs into floats."""
    if isinstance(value, pd.Series):
        non_null = value.dropna()
        if non_null.empty:
            return default
        value = non_null.iloc[0]
    if value is None:
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric):
        return default
    return numeric


def safe_divide(numerator: float | None, denominator: float | None, default: float = 0.0) -> float:
    """Divide two values while avoiding noisy zero/NaN failures."""
    numerator_value = to_float(numerator)
    denominator_value = to_float(denominator)
    if numerator_value is None or denominator_value in (None, 0):
        return default
    return numerator_value / denominator_value


def clip_decimal(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    """Clamp a decimal rate to a reasonable display or model range."""
    return max(lower, min(upper, value))


def format_currency(value: float | None, precision: int = 1) -> str:
    """Format a large currency value for dashboard metrics."""
    numeric = to_float(value)
    if numeric is None:
        return "N/A"
    sign = "-" if numeric < 0 else ""
    absolute = abs(numeric)
    units = [
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ]
    for divisor, suffix in units:
        if absolute >= divisor:
            return f"{sign}${absolute / divisor:,.{precision}f}{suffix}"
    return f"{sign}${absolute:,.0f}"


def format_price(value: float | None, precision: int = 2) -> str:
    """Format a per-share value."""
    numeric = to_float(value)
    if numeric is None:
        return "N/A"
    return f"${numeric:,.{precision}f}"


def format_percent(value: float | None, precision: int = 1) -> str:
    """Format a decimal rate as a percentage."""
    numeric = to_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric * 100:,.{precision}f}%"


def latest_valid(series: pd.Series, default: float | None = None) -> float | None:
    """Return the latest non-null value from a Series sorted by time."""
    if series.empty:
        return default
    non_null = series.dropna()
    if non_null.empty:
        return default
    return to_float(non_null.iloc[-1], default)


def trailing_median(series: pd.Series, periods: int = 3, default: float | None = None) -> float | None:
    """Return a median of the most recent non-null observations."""
    non_null = series.dropna()
    if non_null.empty:
        return default
    return to_float(non_null.tail(periods).median(), default)
