"""The Hargassner Cloud integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CloudApiClient
from .const import (
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_ENABLE_MEASUREMENTS,
    CONF_INSTALLATION,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    PLATFORMS,
)
from .coordinator import CloudCoordinator
from .runtime import CloudRuntimeData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one configured Hargassner account."""
    client = CloudApiClient(
        async_get_clientsession(hass),
        base_url=entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        installation=entry.data[CONF_INSTALLATION],
        client_id=entry.data.get(CONF_CLIENT_ID),
        client_secret=entry.data.get(CONF_CLIENT_SECRET),
    )

    coordinator = CloudCoordinator(
        hass,
        entry,
        client,
        update_interval=int(
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        ),
        enable_measurements=bool(entry.options.get(CONF_ENABLE_MEASUREMENTS)),
    )
    await coordinator.async_config_entry_first_refresh()

    device_metadata = await client.fetch_device_metadata()
    entry.runtime_data = CloudRuntimeData(
        client=client,
        coordinator=coordinator,
        device_metadata=device_metadata,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Release the runtime objects for an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
