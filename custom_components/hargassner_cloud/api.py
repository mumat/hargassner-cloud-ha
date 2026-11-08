"""Async client for the Hargassner Cloud API."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import (
    ClientError,
    ClientSession,
    ClientTimeout,
    ContentTypeError,
)

from .auth import fetch_client_credentials
from .const import (
    BRANDING,
    DEFAULT_CLIENT_ID,
    DEFAULT_CLIENT_SECRET,
    INSTALLATION_RELATIONS,
    LEGACY_TOKEN_PATH,
    LOGIN_PATH,
    LOGOUT_PATH,
    MEASUREMENT_LOOKBACK_HOURS,
    REFRESH_PATH,
    USER_AGENT,
)
from .exceptions import (
    CloudApiError,
    CloudAuthError,
    CloudClientCredentialsError,
    CloudConnectionError,
    CloudMaintenanceError,
)
from .models import Measurement

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=25)
DEFAULT_TOKEN_LIFETIME = 1800.0
TOKEN_REFRESH_AHEAD = 300.0


def _token_payload(body: Any) -> dict[str, Any]:
    """Locate the token object, tolerating an optional ``data`` wrapper."""
    if not isinstance(body, dict):
        return {}
    nested = body.get("data")
    if isinstance(nested, dict) and nested.get("access_token"):
        return nested
    return body


class CloudApiClient:
    """Client for the undocumented Hargassner Cloud REST API."""

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        username: str,
        password: str,
        installation: str,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._installation = str(installation).strip()

        self._client_id = client_id or None
        self._client_secret = client_secret or None
        self._credential_source = "stored" if self._client_id else "none"

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at = 0.0
        self._token_lock = asyncio.Lock()

        self._devices: list[dict[str, Any]] | None = None
        self._metric_fields: dict[str, list[dict[str, Any]]] = {}

        self._diagnostics: dict[str, Any] = {
            "phase": "not_started",
            "outcome": None,
            "http_status": None,
            "credential_source": self._credential_source,
            "error_type": None,
        }

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def diagnostics(self) -> dict[str, Any]:
        """Return structured diagnostics without credentials or values."""
        return dict(self._diagnostics)

    def _record(
        self,
        phase: str,
        outcome: str,
        *,
        http_status: int | None = None,
        error_type: str | None = None,
    ) -> None:
        self._diagnostics.update(
            {
                "phase": phase,
                "outcome": outcome,
                "http_status": http_status,
                "credential_source": self._credential_source,
                "error_type": error_type,
            }
        )

    # ------------------------------------------------------------------
    # Headers
    # ------------------------------------------------------------------

    def _headers(self, authenticated: bool = True) -> dict[str, str]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Branding": BRANDING,
        }
        if authenticated and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _resource_url(self, resource: str) -> str:
        """Build an absolute URL from a widget resource path.

        The portal returns resources relative to the ``/api`` root, but be
        tolerant of values that already include ``/api`` or a full origin.
        """
        if resource.startswith(("http://", "https://")):
            return resource
        if resource.startswith("/api/"):
            return f"{self._base}{resource}"
        return f"{self._base}/api/{resource.lstrip('/')}"

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    async def _refresh_client_credentials(self) -> bool:
        """Try to discover fresh public web-client credentials."""
        try:
            credentials = await fetch_client_credentials(self._session, self._base)
        except CloudMaintenanceError:
            self._record("web_client_credentials", "maintenance")
            raise
        if not credentials:
            return False
        self._client_id, self._client_secret = credentials
        self._credential_source = "discovered"
        return True

    async def _prepare_credentials(self) -> None:
        """Ensure client credentials exist, preferring live discovery."""
        if await self._refresh_client_credentials():
            return
        if self._client_id and self._client_secret:
            if self._credential_source not in {"stored", "embedded"}:
                self._credential_source = "embedded"
            return
        if DEFAULT_CLIENT_ID and DEFAULT_CLIENT_SECRET:
            self._client_id = DEFAULT_CLIENT_ID
            self._client_secret = DEFAULT_CLIENT_SECRET
            self._credential_source = "embedded"
            return
        self._credential_source = "unavailable"
        raise CloudClientCredentialsError(
            "Unable to discover the public Hargassner web-client credentials"
        )

    # ------------------------------------------------------------------
    # Login / token handling
    # ------------------------------------------------------------------

    async def _login_request(self) -> tuple[int, dict[str, Any]]:
        payload: dict[str, Any] = {
            "email": self._username,
            "password": self._password,
        }
        if self._client_id:
            payload["client_id"] = self._client_id
        if self._client_secret:
            payload["client_secret"] = self._client_secret
        return await self._post_json(f"{self._base}{LOGIN_PATH}", payload)

    async def _legacy_login_request(self) -> tuple[int, dict[str, Any]]:
        """Pre-2026 OAuth password grant, kept only as a fallback."""
        payload = {
            "grant_type": "password",
            "client_id": self._client_id or "",
            "client_secret": self._client_secret or "",
            "username": self._username,
            "password": self._password,
        }
        try:
            async with self._session.post(
                f"{self._base}{LEGACY_TOKEN_PATH}",
                data=payload,
                headers=self._headers(authenticated=False),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 200:
                    return response.status, await response.json(content_type=None)
                return response.status, {}
        except (ClientError, TimeoutError) as err:
            raise CloudConnectionError(f"Legacy token request failed: {err}") from err

    async def _post_json(self, url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            async with self._session.post(
                url,
                json=payload,
                headers=self._headers(authenticated=False),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 200:
                    try:
                        return response.status, await response.json(content_type=None)
                    except (ContentTypeError, ValueError, TypeError):
                        return response.status, {}
                return response.status, {}
        except (ClientError, TimeoutError) as err:
            raise CloudConnectionError(f"POST {url} failed: {err}") from err

    async def authenticate(self) -> None:
        """Authenticate and cache the resulting tokens."""
        await self._prepare_credentials()
        status, body = await self._login_request()
        if status == 404:
            _LOGGER.debug("Current login endpoint returned 404; trying legacy token endpoint")
            status, body = await self._legacy_login_request()

        if status in (400, 401, 403) and self._credential_source != "discovered":
            _LOGGER.warning("Login rejected with built-in web-client credentials; re-discovering")
            if await self._refresh_client_credentials():
                status, body = await self._login_request()

        if status in (401, 403, 422):
            if self._credential_source == "discovered":
                self._record("login", "auth_failed", http_status=status)
                raise CloudAuthError(
                    "Authentication failed - check your Hargassner email and password"
                )
            self._record("login", "web_client_credentials_failed", http_status=status)
            raise CloudClientCredentialsError(
                "The Hargassner web-client credentials were rejected and could not be refreshed"
            )
        if status != 200:
            self._record("login", "failed", http_status=status)
            raise CloudConnectionError(f"Login failed: HTTP {status}")

        data = _token_payload(body)
        token = data.get("access_token")
        if not token:
            self._record("login", "invalid_response", http_status=status)
            raise CloudConnectionError("Login response contained no access token")
        self._remember_tokens(data)
        self._record("login", "success", http_status=status)
        _LOGGER.debug("Hargassner login succeeded (credentials: %s)", self._credential_source)

    def _remember_tokens(self, data: dict[str, Any]) -> None:
        self._access_token = str(data["access_token"])
        refresh = data.get("refresh_token")
        if refresh:
            self._refresh_token = str(refresh)
        try:
            expires_in = float(data.get("expires_in") or DEFAULT_TOKEN_LIFETIME)
        except (TypeError, ValueError):
            expires_in = DEFAULT_TOKEN_LIFETIME
        self._expires_at = time.monotonic() + max(expires_in - TOKEN_REFRESH_AHEAD, 60.0)

    def _has_valid_token(self) -> bool:
        return bool(self._access_token) and time.monotonic() < self._expires_at

    def _forget_token(self) -> None:
        self._access_token = None
        self._expires_at = 0.0

    async def _async_refresh(self) -> bool:
        if not self._refresh_token:
            return False
        status, body = await self._post_json(
            f"{self._base}{REFRESH_PATH}",
            {
                "refresh_token": self._refresh_token,
                "client_id": self._client_id or "",
                "client_secret": self._client_secret or "",
            },
        )
        if status != 200:
            _LOGGER.debug("Token refresh failed (HTTP %s); falling back to login", status)
            self._refresh_token = None
            return False
        data = _token_payload(body)
        if not data.get("access_token"):
            self._refresh_token = None
            return False
        self._remember_tokens(data)
        return True

    async def _ensure_token(self) -> None:
        async with self._token_lock:
            if self._has_valid_token():
                return
            if await self._async_refresh():
                return
            await self.authenticate()

    async def sign_out(self) -> None:
        """Best-effort logout; never raises."""
        try:
            await self._post_json(f"{self._base}{LOGOUT_PATH}", {})
        except CloudConnectionError:
            pass
        finally:
            self._forget_token()
            self._refresh_token = None

    # ------------------------------------------------------------------
    # Authenticated requests
    # ------------------------------------------------------------------

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        retry: bool = True,
    ) -> tuple[int, Any]:
        await self._ensure_token()
        retry_needed = False
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 401 and retry:
                    retry_needed = True
                elif response.status >= 400:
                    try:
                        detail = (await response.text())[:200]
                    except (ClientError, ValueError):
                        detail = ""
                    _LOGGER.debug("%s %s -> HTTP %s: %s", method, url, response.status, detail)
                    return response.status, None
                else:
                    try:
                        return response.status, await response.json(content_type=None)
                    except (ContentTypeError, ValueError, TypeError):
                        return response.status, None
        except (ClientError, TimeoutError) as err:
            self._record("request", "failed", error_type=type(err).__name__)
            raise CloudConnectionError(f"{method} {url} failed: {err}") from err

        if retry_needed:
            _LOGGER.debug("401 received for %s; re-authenticating and retrying", url)
            self._forget_token()
            self._refresh_token = None
            return await self._request_json(method, url, params=params, json=json, retry=False)
        return 0, None

    # ------------------------------------------------------------------
    # Installations
    # ------------------------------------------------------------------

    @staticmethod
    def _installations_from_payload(payload: Any) -> list[dict[str, str]]:
        if isinstance(payload, dict):
            items = payload.get("data") or payload.get("installations") or []
        else:
            items = payload
        if not isinstance(items, list):
            return []
        installations: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            identifier = str(item["id"])
            label = item.get("name")
            installations.append(
                {
                    "id": identifier,
                    "name": str(label) if label else f"Installation {identifier}",
                }
            )
        return installations

    async def fetch_installations(self) -> list[dict[str, str]]:
        for path in ("/api/installations", "/api/user/installations"):
            status, payload = await self._request_json("GET", f"{self._base}{path}")
            if status in (401, 403):
                raise CloudAuthError("Installation discovery was rejected")
            if status == 404:
                continue
            if status >= 400:
                raise CloudApiError(status, "installation discovery")
            installations = self._installations_from_payload(payload)
            if installations:
                return installations
        raise CloudConnectionError("This account has no reachable Hargassner installations")

    # ------------------------------------------------------------------
    # Device metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _devices_from_payload(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        root = payload.get("data")
        if not isinstance(root, dict):
            return []
        devices = root.get("devices")
        if not isinstance(devices, list):
            return []
        result: list[dict[str, Any]] = []
        for device in devices:
            if not isinstance(device, dict) or device.get("id") is None:
                continue
            software = device.get("software")
            version = software.get("version_code") if isinstance(software, dict) else None
            io_version = device.get("io_firmware_version")
            result.append(
                {
                    "id": str(device["id"]),
                    "software_version": str(version) if isinstance(version, (int, str)) else None,
                    "io_firmware_version": str(io_version)
                    if isinstance(io_version, (int, str))
                    else None,
                }
            )
        return result

    async def fetch_devices(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        """Return the installation's devices with allowlisted metadata."""
        if self._devices is not None and not refresh:
            return self._devices
        status, payload = await self._request_json(
            "GET",
            f"{self._base}/api/installations/{self._installation}",
            params={"with": INSTALLATION_RELATIONS},
        )
        if status in (403, 404):
            self._devices = []
            return self._devices
        if status >= 400:
            raise CloudApiError(status, "device metadata")
        self._devices = self._devices_from_payload(payload)
        return self._devices

    async def fetch_device_metadata(self) -> dict[str, str]:
        """Return allowlisted version metadata for the device registry."""
        try:
            devices = await self.fetch_devices()
        except (CloudApiError, CloudConnectionError, CloudAuthError):
            return {}
        for device in devices:
            metadata = {
                key: device[key]
                for key in ("software_version", "io_firmware_version")
                if device.get(key)
            }
            if metadata:
                return metadata
        return {}

    # ------------------------------------------------------------------
    # Widgets
    # ------------------------------------------------------------------

    async def fetch_widgets(self) -> dict[str, Any]:
        """Fetch the installation's current widget state."""
        status, payload = await self._request_json(
            "GET", f"{self._base}/api/installations/{self._installation}/widgets"
        )
        if status in (401, 403):
            raise CloudAuthError("CloudWidget request was rejected")
        if status >= 400:
            # Fallback endpoint; never advanced to after an auth failure.
            status, payload = await self._request_json(
                "GET",
                f"{self._base}/api/widgets",
                params={"installationId": self._installation},
            )
        if status in (401, 403):
            raise CloudAuthError("CloudWidget request was rejected")
        if status >= 400:
            self._record("widgets", "failed", http_status=status)
            raise CloudApiError(status, "widgets")
        if not isinstance(payload, dict):
            self._record("widgets", "invalid_response", http_status=status)
            raise CloudConnectionError("CloudWidget response was not valid JSON")
        self._record("widgets", "success", http_status=status)
        return payload

    # ------------------------------------------------------------------
    # Measurements (optional)
    # ------------------------------------------------------------------

    async def _metric_fields_for_device(self, device_id: str) -> list[dict[str, Any]]:
        if device_id in self._metric_fields:
            return self._metric_fields[device_id]
        status, payload = await self._request_json(
            "GET", f"{self._base}/api/devices/{device_id}/metric-fields"
        )
        if status >= 400 or not isinstance(payload, dict):
            self._metric_fields[device_id] = []
            return []
        fields: list[dict[str, Any]] = []
        data = payload.get("data")
        if isinstance(data, list):
            for group in data:
                if not isinstance(group, dict):
                    continue
                group_name = group.get("text") or group.get("type")
                group_fields = group.get("fields")
                if not isinstance(group_fields, list):
                    continue
                for field in group_fields:
                    if isinstance(field, dict) and field.get("id") is not None:
                        fields.append({**field, "_group": group_name})
        self._metric_fields[device_id] = fields
        return fields

    async def _latest_samples(self, device_id: str, channels: list[str]) -> dict[str, Any]:
        now = datetime.now(UTC)
        params = {
            "channels": ";".join(channels),
            "from": (now - timedelta(hours=MEASUREMENT_LOOKBACK_HOURS)).isoformat(),
            "to": now.isoformat(),
        }
        status, payload = await self._request_json(
            "GET",
            f"{self._base}/api/devices/{device_id}/measurements",
            params=params,
        )
        if status >= 400 or not isinstance(payload, dict):
            return {}
        samples = payload.get("data")
        if not isinstance(samples, list):
            return {}
        latest: dict[str, Any] = {}
        wanted = set(channels)
        for sample in reversed(samples):
            values = sample.get("values") if isinstance(sample, dict) else None
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                channel = str(key)
                if channel in wanted and channel not in latest and value is not None:
                    latest[channel] = value
            if len(latest) == len(wanted):
                break
        return latest

    async def fetch_measurements(self) -> list[Measurement]:
        """Fetch the latest value of every active measurement channel."""
        devices = await self.fetch_devices()
        results: list[Measurement] = []
        for device in devices:
            device_id = str(device["id"])
            fields = await self._metric_fields_for_device(device_id)
            channels = [str(field["id"]) for field in fields if field.get("id") is not None]
            if not channels:
                continue
            latest = await self._latest_samples(device_id, channels)
            for field in fields:
                channel_id = str(field["id"])
                results.append(
                    Measurement(
                        key=f"{device_id}_{channel_id}",
                        name=str(field.get("legend") or field.get("text") or channel_id),
                        unit=str(field["unit"]) if field.get("unit") else None,
                        value=latest.get(channel_id),
                        device_id=device_id,
                        channel_id=channel_id,
                        group=str(field["_group"]) if field.get("_group") else None,
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def write_parameter(self, resource: str, value: Any) -> None:
        """Write a parameter using the resource URL from the API payload."""
        url = self._resource_url(resource)
        status, _ = await self._request_json("PATCH", url, json={"value": value})
        if status not in (200, 204):
            self._record("patch", "failed", http_status=status)
            raise CloudApiError(status, f"PATCH {resource}")
        self._record("patch", "success", http_status=status)
        _LOGGER.debug("PATCH %s = %r [%s]", resource, value, status)

    async def run_action(self, resource: str) -> None:
        """Trigger an action using the resource URL from the API payload."""
        url = self._resource_url(resource)
        status, _ = await self._request_json("POST", url)
        if status not in (200, 204):
            self._record("action", "failed", http_status=status)
            raise CloudApiError(status, f"POST {resource}")
        self._record("action", "success", http_status=status)
        _LOGGER.debug("POST %s [%s]", resource, status)
