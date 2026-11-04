"""System health support for the Hargassner Cloud integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import CONF_BASE_URL, DEFAULT_BASE_URL, DOMAIN


@callback
def async_register(
    hass: HomeAssistant, register: system_health.SystemHealthRegistration
) -> None:
    """Register Hargassner Cloud system health information."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return non-sensitive integration health information."""
    entries = hass.config_entries.async_entries(DOMAIN)
    base_url = (
        entries[0].data.get(CONF_BASE_URL, DEFAULT_BASE_URL)
        if entries
        else DEFAULT_BASE_URL
    )
    return {
        "configured_entries": len(entries),
        "can_reach_server": system_health.async_check_can_reach_url(hass, base_url),
    }
