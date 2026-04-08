"""Custom exception types for the TrainingPeaks sync feature.

Using specific types instead of generic Exception makes the UI layer able
to render targeted error messages (auth vs API vs conversion) and lets
tests assert on the failure mode precisely.
"""
from __future__ import annotations


class TPError(Exception):
    """Base class for all TrainingPeaks sync errors."""


class TPAuthError(TPError):
    """Raised when TrainingPeaks authentication fails.

    Typical causes: missing TP_AUTH_COOKIE, expired session cookie, or
    401/403 response from the token endpoint. The UI should prompt the
    user to refresh their cookie from DevTools.
    """


class TPAPIError(TPError):
    """Raised on any non-auth TrainingPeaks API failure.

    Covers 4xx (not auth), 5xx, timeouts, and network errors. Carries the
    HTTP status code when available for logging / retry decisions.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TPConversionError(TPError):
    """Raised when an intervals.icu workout_doc can't be mapped to TP format.

    Examples: missing FTP for POWER-targeted workout, empty steps array,
    unknown target type, distance-based steps (out of MVP scope), or a
    step missing its resolved target values.
    """
