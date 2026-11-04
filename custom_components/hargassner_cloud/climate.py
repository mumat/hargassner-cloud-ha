"""Thermostat entities, one per heating circuit."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .adapters import to_float
from .coordinator import CloudCoordinator
from .entity import CloudEntity
from .helpers import normalize_widget_number
from .models import CloudParameter, CloudWidget

_LOGGER = logging.getLogger(__name__)

OFF_MODE = "MODE_OFF"
DEFAULT_MODE = "MODE_AUTOMATIC"
_SETPOINT_KEYS = ("room_temperature_heating", "room_temperature_target")


def _find_setpoint(widget: CloudWidget) -> CloudParameter | None:
    for key in _SETPOINT_KEYS:
        parameter = widget.parameter(key)
        if parameter is not None and parameter.writable:
            return parameter
    return None


def _find_circuit_mode(widget: CloudWidget) -> CloudParameter | None:
    parameter = widget.parameter("mode")
    return parameter if parameter is not None and parameter.writable else None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: CloudCoordinator = entry.runtime_data.coordinator
    data = coordinator.data
    if data is None:
        async_add_entities([])
        return

    entities: list[CloudThermostat] = []
    seen: set[int] = set()
    for widget in data.heating_circuits():
        number = normalize_widget_number(widget.number)
        if number is None or number in seen:
            continue
        if _find_setpoint(widget) is None:
            continue
        seen.add(number)
        entities.append(CloudThermostat(coordinator, entry, widget.type, str(number)))
    async_add_entities(entities)


class CloudThermostat(CloudEntity, ClimateEntity):
    """A thermostat for one heating circuit."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 10.0
    _attr_max_temp = 30.0

    def __init__(
        self,
        coordinator: CloudCoordinator,
        entry: ConfigEntry,
        widget_type: str,
        number: str,
    ) -> None:
        super().__init__(coordinator, entry, f"hc{number}_climate")
        self._widget_type = widget_type
        self._number = number
        self._attr_translation_key = "heating_circuit"
        self._attr_translation_placeholders = {"number": number}

    @property
    def _widget(self) -> CloudWidget | None:
        data = self.coordinator.data
        return data.widget(self._widget_type, self._number) if data else None

    @property
    def _setpoint(self) -> CloudParameter | None:
        widget = self._widget
        return _find_setpoint(widget) if widget else None

    @property
    def _circuit_mode(self) -> CloudParameter | None:
        widget = self._widget
        return _find_circuit_mode(widget) if widget else None

    @property
    def available(self) -> bool:
        return super().available and self._setpoint is not None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if self._circuit_mode is not None:
            features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        return features

    @property
    def hvac_modes(self) -> list[HVACMode]:
        if self._circuit_mode is None:
            return [HVACMode.HEAT]
        return [HVACMode.HEAT, HVACMode.OFF]

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self._circuit_mode
        if mode is not None and mode.value == OFF_MODE:
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def current_temperature(self) -> float | None:
        widget = self._widget
        return to_float(widget.value("room_temperature_current")) if widget else None

    @property
    def target_temperature(self) -> float | None:
        setpoint = self._setpoint
        return to_float(setpoint.value) if setpoint else None

    @property
    def min_temp(self) -> float:
        setpoint = self._setpoint
        if setpoint and setpoint.minimum is not None:
            return setpoint.minimum
        return self._attr_min_temp

    @property
    def max_temp(self) -> float:
        setpoint = self._setpoint
        if setpoint and setpoint.maximum is not None:
            return setpoint.maximum
        return self._attr_max_temp

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        setpoint = self._setpoint
        if setpoint is None or not setpoint.resource:
            raise HomeAssistantError(f"{self.entity_id}: setpoint is not writable")
        await self.coordinator.client.write_parameter(setpoint.resource, temperature)
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        mode = self._circuit_mode
        if mode is None or not mode.resource:
            raise HomeAssistantError(f"{self.entity_id}: mode is not writable")
        value = OFF_MODE if hvac_mode == HVACMode.OFF else DEFAULT_MODE
        await self.coordinator.client.write_parameter(mode.resource, value)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
