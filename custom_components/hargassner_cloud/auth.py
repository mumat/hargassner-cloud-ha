"""Resolve the web application's public OAuth client credentials.

The ``client_id``/``client_secret`` belong to the Hargassner web frontend and
travel with the account credentials; they are not personal secrets. Because the
frontend is rebuilt regularly, the values are read from the live assets, with
the constants in :mod:`const` used as a fallback. Keeping this logic in one place
makes it easy to test and to replace.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    BRANDING,
    LOGIN_PAGE_PATH,
    USER_AGENT,
    VITE_MANIFEST_PATH,
)
from .exceptions import CloudMaintenanceError

_LOGGER = logging.getLogger(__name__)

_BUNDLE_SCRIPT_RE = re.compile(
    r"""<script[^>]+src=["']([^"']*?/build/assets/app-[^"']+\.js)["']"""
)
_LOGIN_CALL_SITE_RE = re.compile(
    r"static login\(\w+,\w+\)\{return \w+\.login\(\w+,\w+,([\w$]+),([\w$]+)\)\}"
)
_CREDENTIAL_PAIR_RE = re.compile(r"client_id:([\w$]+),client_secret:([\w$]+)")
_LEGACY_PAIR_RE = re.compile(r'o="(\d+)",n="([^"]+)"')
_MAINTENANCE_TITLE_RE = re.compile(
    r"<title[^>]*>[^<]*(?:wartungsarbeiten|maintenance)[^<]*</title>",
    re.IGNORECASE,
)


def _headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Branding": BRANDING,
        "Accept": "application/json, text/html",
    }


async def _get_text(
    session: ClientSession, url: str, timeout: int = 20
) -> str | None:
    """Fetch a URL as text, returning ``None`` on any failure."""
    try:
        async with session.get(
            url, headers=_headers(), timeout=ClientTimeout(total=timeout)
        ) as response:
            if response.status >= 400:
                _LOGGER.debug("GET %s -> HTTP %s", url, response.status)
                return None
            return await response.text()
    except (ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("GET %s failed: %s", url, err)
        return None


def _resolve_literal(bundle: str, variable: str) -> str | None:
    """Resolve a minified variable to its assigned string literal."""
    match = re.search(
        rf"""(?:^|[,;]|\b(?:const|let|var)\s+){re.escape(variable)}=["']([^"']+)["']""",
        bundle,
    )
    return match.group(1) if match else None


def parse_client_credentials(bundle: str) -> tuple[str, str] | None:
    """Extract credentials by anchoring on the login call site."""
    anchor = _LOGIN_CALL_SITE_RE.search(bundle) or _CREDENTIAL_PAIR_RE.search(bundle)
    if anchor:
        client_id = _resolve_literal(bundle, anchor.group(1))
        client_secret = _resolve_literal(bundle, anchor.group(2))
        if client_id and client_secret:
            return client_id, client_secret

    legacy = _LEGACY_PAIR_RE.search(bundle)
    if legacy:
        return legacy.group(1), legacy.group(2)
    return None


async def _credentials_in_bundle(
    session: ClientSession, base: str, bundle_url: str
) -> tuple[str, str] | None:
    bundle = await _get_text(session, bundle_url)
    if not bundle:
        return None
    return parse_client_credentials(bundle)


async def _credentials_in_manifest(
    session: ClientSession, base: str
) -> tuple[str, str] | None:
    """Discover the current hashed entry bundle via the Vite manifest."""
    try:
        async with session.get(
            f"{base}{VITE_MANIFEST_PATH}",
            headers=_headers(),
            timeout=ClientTimeout(total=15),
        ) as response:
            if response.status != 200:
                return None
            manifest = await response.json(content_type=None)
    except (ClientError, TimeoutError, ValueError, TypeError) as err:
        _LOGGER.debug("Vite manifest discovery failed: %s", err)
        return None

    if not isinstance(manifest, dict):
        return None
    entry = next(
        (
            value["file"]
            for value in manifest.values()
            if isinstance(value, dict)
            and value.get("isEntry")
            and str(value.get("file", "")).endswith(".js")
        ),
        None,
    )
    if not entry:
        return None
    return await _credentials_in_bundle(session, base, f"{base}/build/{entry}")


async def fetch_client_credentials(
    session: ClientSession, base_url: str
) -> tuple[str, str] | None:
    """Discover the public web-client credentials from the live frontend.

    Raises :class:`CloudMaintenanceError` when the portal serves its
    maintenance page, so callers can distinguish an outage from a rotation.
    """
    base = base_url.rstrip("/")

    credentials = await _credentials_in_manifest(session, base)
    if credentials:
        _LOGGER.debug("Discovered web-client credentials via the Vite manifest")
        return credentials

    html = await _get_text(session, f"{base}{LOGIN_PAGE_PATH}")
    if html:
        script = _BUNDLE_SCRIPT_RE.search(html)
        if script:
            credentials = await _credentials_in_bundle(
                session, base, urljoin(f"{base}/", script.group(1))
            )
            if credentials:
                _LOGGER.debug("Discovered web-client credentials via the login page")
                return credentials
        elif _MAINTENANCE_TITLE_RE.search(html):
            raise CloudMaintenanceError(
                "Hargassner Cloud is down for scheduled maintenance"
            )

    credentials = await _credentials_in_bundle(session, base, f"{base}/js/app.js")
    if credentials:
        _LOGGER.debug("Discovered web-client credentials via the legacy bundle")
    return credentials
