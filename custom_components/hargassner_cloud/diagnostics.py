"""Diagnostics support for the Hargassner Cloud integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_INSTALLATION,
    CONF_PASSWORD,
    CONF_USERNAME,
)

REDACT_KEYS = {
    CONF_PASSWORD,
    CONF_CLIENT_SECRET,
    CONF_CLIENT_ID,
    CONF_USERNAME,
    CONF_INSTALLATION,
    "access_token",
    "refresh_token",
    "token",
    "authorization",
    "email",
    "name",
    "address",
    "area",
    "location",
    "coordinates",
    "serial_number",
}


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _summarize_state(payload: object) -> dict[str, Any]:
    """Reduce the widget response to keys and types, never operational values."""
    if not isinstance(payload, dict):
        return {"payload_type": _json_type(payload)}

    widgets: list[dict[str, Any]] = []
    device: dict[str, str] = {}
    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                widgets.append({"item_type": _json_type(item)})
                continue
            widget: dict[str, Any] = {}
            if isinstance(item.get("widget"), str):
                widget["widget"] = item["widget"]
            if isinstance(item.get("number"), (int, str)):
                widget["number"] = str(item["number"])
            values = item.get("values")
            if isinstance(values, dict):
                if item.get("widget") == "HEATER" and isinstance(
                    values.get("device_type"), str
                ):
                    device["type"] = values["device_type"]
                widget["values"] = {
                    str(key): _json_type(value) for key, value in values.items()
                }
            parameters = item.get("parameters")
            if isinstance(parameters, dict):
                widget["parameters"] = sorted(str(key) for key in parameters)
            actions = item.get("actions")
            if isinstance(actions, dict):
                widget["actions"] = sorted(str(key) for key in actions)
            widgets.append(widget)

    meta = payload.get("meta")
    meta_fields = (
        {str(key): _json_type(value) for key, value in meta.items()}
        if isinstance(meta, dict)
        else {}
    )
    return {"device": device, "widgets": widgets, "meta": meta_fields}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Build a redacted diagnostics snapshot for one entry."""
    redacted_entry = {
        "entry_data": async_redact_data(dict(entry.data), REDACT_KEYS),
        "options": async_redact_data(dict(entry.options), REDACT_KEYS),
    }

    runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data is None:
        return {
            "entry": redacted_entry,
            "last_update_succeeded": None,
            "api": {"phase": "setup", "outcome": "not_loaded"},
            "payload_shape": {"device": {}, "widgets": [], "meta": {}},
        }

    coordinator = runtime_data.coordinator
    payload = _summarize_state(coordinator.data.raw if coordinator.data else {})
    device = payload.get("device")
    if isinstance(device, dict):
        device.update(getattr(runtime_data, "device_metadata", {}) or {})

    return {
        "entry": redacted_entry,
        "last_update_succeeded": coordinator.last_update_success,
        "api": async_redact_data(runtime_data.client.diagnostics, REDACT_KEYS),
        "payload_shape": payload,
    }
