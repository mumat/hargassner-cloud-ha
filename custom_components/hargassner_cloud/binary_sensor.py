"""Binary sensor entities for the Hargassner Cloud integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .adapters import to_bool
from .const import (
    CONF_FIELD_OVERRIDES,
    TYPE_BOILER,
    TYPE_BUFFER,
    TYPE_HEATER,
)
from .coordinator import CloudCoordinator
from .entity import CloudEntity, read_override
from .helpers import first_defined, parse_field_overrides, normalize_widget_number
from .models import InstallationState


@dataclass(frozen=True, kw_only=True)
class BinarySensorDefinition(BinarySensorEntityDescription):
    """Describes a Hargassner binary sensor."""

    value_fn: Callable[[InstallationState], bool | None] | None = None


def _action_state(
    data: InstallationState, widget_type: str, action_key: str, number: str | None = None
) -> bool | None:
    """Return the action's disabled flag.

    An in-progress force-charge disables its own trigger, so ``disabled`` is
    used as a fallback for the ``*_force_charging_active`` state.
    """
    widget = data.widget(widget_type, number)
    action = widget.action(action_key) if widget else None
    return action.disabled if action else None


def boiler_sensors(num: int) -> list[BinarySensorDefinition]:
    number = str(num)
    return [
        BinarySensorDefinition(
            key=f"boiler{num}_pump",
            translation_key="boiler_pump",
            translation_placeholders={"number": number},
            device_class=BinarySensorDeviceClass.RUNNING,
            value_fn=lambda d: to_bool(d.value(TYPE_BOILER, "pump_active", number)),
        ),
        BinarySensorDefinition(
            key=f"boiler{num}_force_charge",
            translation_key="boiler_force_charge",
            translation_placeholders={"number": number},
            device_class=BinarySensorDeviceClass.RUNNING,
            value_fn=lambda d: to_bool(
                first_defined(
                    d.value(TYPE_BOILER, "force_charging_active", number),
                    _action_state(d, TYPE_BOILER, "force_charging", number),
                )
            ),
        ),
    ]


def heating_circuit_sensors(
    widget_type: str, num: int
) -> list[BinarySensorDefinition]:
    number = str(num)
    return [
        BinarySensorDefinition(
            key=f"hc{num}_pump",
            translation_key="circuit_pump",
            translation_placeholders={"number": number},
            device_class=BinarySensorDeviceClass.RUNNING,
            value_fn=lambda d: to_bool(d.value(widget_type, "pump_active", number)),
        ),
        BinarySensorDefinition(
            key=f"hc{num}_running",
            translation_key="circuit_running",
            translation_placeholders={"number": number},
            device_class=BinarySensorDeviceClass.RUNNING,
            value_fn=lambda d: to_bool(d.value(widget_type, "active", number)),
        ),
    ]


def build_definitions(data: InstallationState) -> list[BinarySensorDefinition]:
    """Build binary descriptions from the widgets actually returned."""
    descriptions: list[BinarySensorDefinition] = [
        BinarySensorDefinition(
            key="cloud_connection",
            translation_key="cloud_connection",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d: d.online,
        )
    ]

    if data.widget(TYPE_HEATER) is not None:
        descriptions.append(
            BinarySensorDefinition(
                key="heater_running",
                translation_key="heater_running",
                device_class=BinarySensorDeviceClass.POWER,
                value_fn=lambda d: (
                    None
                    if d.value(TYPE_HEATER, "state") is None
                    else d.value(TYPE_HEATER, "state") != "STATE_OFF"
                ),
            )
        )
        descriptions.append(
            BinarySensorDefinition(
                key="exhaust_guard",
                translation_key="exhaust_guard",
                device_class=BinarySensorDeviceClass.SAFETY,
                entity_category=EntityCategory.DIAGNOSTIC,
                value_fn=lambda d: to_bool(d.value(TYPE_HEATER, "heater_exhaust_guard")),
            )
        )

    if data.widget(TYPE_BUFFER) is not None:
        descriptions.append(
            BinarySensorDefinition(
                key="buffer_pump",
                translation_key="buffer_pump",
                device_class=BinarySensorDeviceClass.RUNNING,
                value_fn=lambda d: to_bool(d.value(TYPE_BUFFER, "pump_active")),
            )
        )
        descriptions.append(
            BinarySensorDefinition(
                key="buffer_force_charge",
                translation_key="buffer_force_charge",
                device_class=BinarySensorDeviceClass.RUNNING,
                value_fn=lambda d: to_bool(
                    first_defined(
                        d.value(TYPE_BUFFER, "force_charging_active"),
                        _action_state(d, TYPE_BUFFER, "force_charging"),
                    )
                ),
            )
        )

    seen_boilers: set[int] = set()
    for widget in data.boilers():
        number = normalize_widget_number(widget.number, default=1)
        if number is None or number in seen_boilers:
            continue
        seen_boilers.add(number)
        descriptions.extend(boiler_sensors(number))

    seen_circuits: set[int] = set()
    for widget in data.heating_circuits():
        number = normalize_widget_number(widget.number)
        if number is None or number in seen_circuits:
            continue
        seen_circuits.add(number)
        descriptions.extend(heating_circuit_sensors(widget.type, number))

    return descriptions


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: CloudCoordinator = entry.runtime_data.coordinator
    data = coordinator.data
    overrides = parse_field_overrides(entry.options.get(CONF_FIELD_OVERRIDES))
    if data is None:
        async_add_entities([])
        return
    entities = [
        CloudBinarySensor(coordinator, entry, description, overrides.get(description.key))
        for description in build_definitions(data)
    ]
    async_add_entities(entities)


class CloudBinarySensor(CloudEntity, BinarySensorEntity):
    """A binary sensor backed by a widget value."""

    entity_description: BinarySensorDefinition

    def __init__(
        self,
        coordinator: CloudCoordinator,
        entry: ConfigEntry,
        description: BinarySensorDefinition,
        override: dict[str, str] | None,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._description = description
        self._override = override

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if self._override:
            return to_bool(read_override(data, self._override))
        if self._description.value_fn is None:
            return None
        return self._description.value_fn(data) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if data is None:
            return None
        allowed = ("online_state", "refreshed", "timestamp", "source")
        return {key: data.meta[key] for key in allowed if key in data.meta} or None
