"""Custom exceptions for DCF Valuation Studio."""


class DCFStudioError(Exception):
    """Base exception for DCF Valuation Studio."""


class DataUnavailableError(DCFStudioError):
    """Raised when required market or financial statement data is unavailable."""


class ValuationInputError(DCFStudioError):
    """Raised when valuation inputs are mathematically invalid."""
