from __future__ import annotations


class WikiTreeAPIError(RuntimeError):
    """Base exception for WikiTree API client failures."""


class WikiTreeHTTPError(WikiTreeAPIError):
    """Raised for HTTP-level failures (non-2xx responses, network errors, etc.)."""


class WikiTreeStatusError(WikiTreeAPIError):
    """Raised when the API returns a non-success ``status`` value."""
