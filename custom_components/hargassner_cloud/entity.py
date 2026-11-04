"""Shared entity base for the Hargassner Cloud integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_AREA,
    CONF_BASE_URL,
    CONF_INSTALLATION,
    DEFAULT_BASE_URL,
    DOMAIN,
    MANUFACTURER,
    NAME,
)
from .coordinator import CloudCoordinator
from .models import InstallationState


class CloudEntity(CoordinatorEntity[CloudCoordinator]):
    """Base class for all Hargassner Cloud entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CloudCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def installation_id(self) -> str:
        return str(self._entry.data.get(CONF_INSTALLATION, self._entry.entry_id))

    @property
    def device_info(self) -> DeviceInfo:
        data: InstallationState | None = self.coordinator.data
        runtime = getattr(self._entry, "runtime_data", None)
        metadata = getattr(runtime, "device_metadata", None) or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self.installation_id)},
            manufacturer=MANUFACTURER,
            model=data.device_model if data else "Hargassner",
            name=data.device_name if data else NAME,
            sw_version=metadata.get("software_version"),
            configuration_url=self._entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
            suggested_area=self._entry.options.get(CONF_AREA) or self._entry.data.get(CONF_AREA),
        )

    @property
    def data(self) -> InstallationState | None:
        return self.coordinator.data


def read_override(data: InstallationState | None, override: dict[str, str] | None) -> Any:
    """Return the raw value selected by a field override, if any."""
    if data is None or not override:
        return None
    widget = override.get("widget")
    field = override.get("field")
    if not widget or not field:
        return None
    return data.value(widget, field, override.get("number"))
