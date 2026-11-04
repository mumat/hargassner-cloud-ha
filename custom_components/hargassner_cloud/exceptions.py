"""Exceptions for the Hargassner Cloud integration."""

from __future__ import annotations


class CloudError(Exception):
    """Base exception for all Hargassner Cloud errors."""


class CloudAuthError(CloudError):
    """Raised when the user's own credentials are rejected.

    This is a personal authentication failure and should start Home Assistant's
    reauthentication flow.
    """


class CloudConnectionError(CloudError):
    """Raised on transport or response-parsing failures against the portal."""


class CloudMaintenanceError(CloudConnectionError):
    """Raised when Hargassner explicitly reports scheduled maintenance.

    This is a transient outage and must not trigger reauthentication or a
    credential repair issue.
    """


class CloudClientCredentialsError(CloudError):
    """Raised when the public web-client credentials are unavailable or rejected.

    This is not caused by the user's password and must not start the
    reauthentication flow; Home Assistant should create a repair issue instead.
    """


class CloudApiError(CloudError):
    """Raised when an authenticated API request returns an unexpected status."""

    def __init__(self, status: int, message: str = "") -> None:
        self.status = status
        super().__init__(
            f"API returned {status}: {message}" if message else f"API returned {status}"
        )
