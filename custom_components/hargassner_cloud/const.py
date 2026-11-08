"""Constants for the Hargassner Cloud integration."""

from __future__ import annotations

DOMAIN = "hargassner_cloud"
NAME = "Hargassner Cloud"
MANUFACTURER = "Hargassner"

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "number",
    "select",
    "switch",
    "button",
    "climate",
]

# ---------------------------------------------------------------------------
# Config entry keys
# ---------------------------------------------------------------------------
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_INSTALLATION = "installation"
CONF_BASE_URL = "base_url"
CONF_AREA = "area"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"

# ---------------------------------------------------------------------------
# Options keys
# ---------------------------------------------------------------------------
CONF_SCAN_INTERVAL = "scan_interval_seconds"
CONF_FIELD_OVERRIDES = "field_overrides_json"
CONF_EXPOSE_ALL_PARAMETERS = "expose_all_parameters"
CONF_ENABLE_MEASUREMENTS = "enable_measurements"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://web.hargassner.at"
DEFAULT_SCAN_INTERVAL = 300
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 3600

# ---------------------------------------------------------------------------
# Public web-client credentials.
#
# These identifiers belong to the Hargassner web application itself and are sent
# together with the account email and password; they are not personal secrets.
# The client prefers values it discovers from the live frontend and only uses the
# constants below as a starting point.
# ---------------------------------------------------------------------------
DEFAULT_CLIENT_ID = "1"
DEFAULT_CLIENT_SECRET = "aSYsAYj7Gsl5v9tPEDdS1hhXTUezgJk1NhOZ1bHR"
BRANDING = "BRANDING_HARGASSNER"
USER_AGENT = "hargassner-cloud-ha/0.1.1 (+https://github.com/mumat/hargassner-cloud-ha)"

# ---------------------------------------------------------------------------
# CloudWidget types
# ---------------------------------------------------------------------------
TYPE_HEATER = "HEATER"
TYPE_BUFFER = "BUFFER"
TYPE_BOILER = "BOILER"
TYPE_HEATING_CIRCUIT = "HEATING_CIRCUIT"
TYPE_HEATING_CONTROLLER = "HEATING_CIRCUIT_CONTROLLER"
TYPE_EVENTS = "EVENTS"

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
INSTALLATION_RELATIONS = (
    "devices.gateway;devices.gateway.software;devices.software;devices.software.type"
)

MEASUREMENT_LOOKBACK_HOURS = 24

# Kept as an escape hatch for the (currently removed) OAuth password grant.
LEGACY_TOKEN_PATH = "/oauth/token"
LOGIN_PATH = "/api/auth/login"
REFRESH_PATH = "/api/auth/refresh"
LOGOUT_PATH = "/api/auth/logout"
LOGIN_PAGE_PATH = "/login"
VITE_MANIFEST_PATH = "/build/manifest.json"

# ---------------------------------------------------------------------------
# Repair issues
# ---------------------------------------------------------------------------
ISSUE_WEB_CLIENT_CREDENTIALS = "web_client_credentials"
ISSUE_URL = "https://github.com/mumat/hargassner-cloud-ha/issues"
