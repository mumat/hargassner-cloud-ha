"""Sensor entities for the Hargassner Cloud integration."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .adapters import to_float, to_str
from .const import (
    CONF_FIELD_OVERRIDES,
    TYPE_BOILER,
    TYPE_BUFFER,
    TYPE_HEATER,
    TYPE_HEATING_CONTROLLER,
)
from .coordinator import CloudCoordinator
from .entity import CloudEntity, read_override
from .helpers import first_defined, normalize_enum, normalize_widget_number, parse_field_overrides
from .models import InstallationState, Measurement

# ---------------------------------------------------------------------------
# Enumerations exposed by the API
# ---------------------------------------------------------------------------

HEATER_STATES = [
    "off",
    "on",
    "ignition",
    "ignition_wait",
    "efficiency_fire",
    "throttle_efficiency_fire",
    "burn_out",
    "embers_keeping",
    "residual_heating",
    "overheating",
    "deashing",
    "filling",
    "overheat_protection",
    "manual",
    "door_open",
    "door_closed",
    "block_protection",
    "ash_drawer_open",
    "burn_assistant",
    "backup_mode_logs",
]
HEATER_PROGRAMS = [
    "automatic",
    "boiler",
    "chimney_sweeper",
    "combination_off",
    "combination_on",
    "manual",
    "off",
    "pellets_disabled",
    "stop_firing",
]
BUFFER_STATES = [
    "off",
    "on",
    "boiler_charging",
    "charging",
    "ignore_request",
    "manual",
    "residual_heating",
]
BOILER_STATES = [
    "off",
    "on",
    "boiler_charging",
    "manual",
    "overheating",
    "residual_heating",
    "block_protection",
]
CIRCUIT_STATES = [
    "off",
    "on",
    "heating",
    "cooling",
    "reduction_transition",
    "reduction",
    "daily_nightly_deactivation",
    "summer_deactivation",
    "freeze_protection",
    "screed_heating",
    "manual",
    "residual_heating",
    "solar_heating",
    "boiler_charging",
]
CIRCUIT_MODES = [
    "automatic",
    "off",
    "heating",
    "reduction",
    "cooling",
    "dry_out",
    "bridge_heating",
    "bridge_reduction",
    "circulation",
    "hv",
    "pk",
    "hv_pk",
    "logs",
]


def _enum_state(
    data: InstallationState, widget_type: str, field: str, number: str | None, options: list[str]
) -> str | None:
    return normalize_enum(data.value(widget_type, field, number), options, "STATE")


def _heater_program(data: InstallationState) -> str | None:
    return normalize_enum(data.parameter_value(TYPE_HEATER, "program"), HEATER_PROGRAMS, "PROGRAM")


def _circuit_mode(data: InstallationState, widget_type: str, number: str) -> str | None:
    return normalize_enum(
        data.parameter_value(widget_type, "mode", number),
        CIRCUIT_MODES,
        "MODE",
    )


def _outdoor_temp(data: InstallationState) -> float | None:
    """Read the outdoor temperature from whichever widget exposes it."""
    candidates: list[Any] = [data.value(TYPE_HEATER, "outdoor_temperature")]
    for circuit in data.heating_circuits():
        candidates.append(circuit.value("outdoor_temperature"))
    candidates.append(data.value(TYPE_HEATING_CONTROLLER, "outdoor_temperature"))
    return to_float(first_defined(*candidates))


def _outdoor_temp_avg(data: InstallationState) -> float | None:
    candidates: list[Any] = [data.value(TYPE_HEATER, "outdoor_temperature_average")]
    for circuit in data.heating_circuits():
        candidates.append(circuit.value("outdoor_temperature_average"))
    candidates.append(data.value(TYPE_HEATING_CONTROLLER, "outdoor_temperature_average"))
    return to_float(first_defined(*candidates))


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class SensorDefinition(SensorEntityDescription):
    """Describes a Hargassner sensor."""

    value_fn: Callable[[InstallationState], Any] | None = None


def heater_sensors() -> list[SensorDefinition]:
    return [
        SensorDefinition(
            key="heater_state",
            translation_key="heater_status",
            icon="mdi:fire",
            device_class=SensorDeviceClass.ENUM,
            options=HEATER_STATES,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d: _enum_state(d, TYPE_HEATER, "state", None, HEATER_STATES),
        ),
        SensorDefinition(
            key="heater_program",
            translation_key="heater_operation",
            icon="mdi:cog",
            device_class=SensorDeviceClass.ENUM,
            options=HEATER_PROGRAMS,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=_heater_program,
        ),
        SensorDefinition(
            key="heater_smoke_temp",
            translation_key="flue_gas_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_HEATER, "smoke_temperature")),
        ),
        SensorDefinition(
            key="heater_temp_current",
            translation_key="heater_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_HEATER, "heater_temperature_current")),
        ),
        SensorDefinition(
            key="heater_temp_target",
            translation_key="heater_temperature_target",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_HEATER, "heater_temperature_target")),
        ),
        SensorDefinition(
            key="heater_efficiency",
            translation_key="combustion_efficiency",
            icon="mdi:percent",
            native_unit_of_measurement="%",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_HEATER, "efficiency")),
        ),
        SensorDefinition(
            key="heater_fuel_stock",
            translation_key="fuel_stock",
            icon="mdi:sack",
            native_unit_of_measurement="kg",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(
                first_defined(
                    d.value(TYPE_HEATER, "fuel_stock"),
                    d.parameter_value(TYPE_HEATER, "fuel_stock"),
                )
            ),
        ),
        SensorDefinition(
            key="outdoor_temp",
            translation_key="outdoor_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=_outdoor_temp,
        ),
        SensorDefinition(
            key="outdoor_temp_avg",
            translation_key="outdoor_temperature_average",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=_outdoor_temp_avg,
        ),
    ]


def buffer_sensors() -> list[SensorDefinition]:
    return [
        SensorDefinition(
            key="buffer_state",
            translation_key="buffer_status",
            icon="mdi:water-boiler",
            device_class=SensorDeviceClass.ENUM,
            options=BUFFER_STATES,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d: _enum_state(d, TYPE_BUFFER, "state", None, BUFFER_STATES),
        ),
        SensorDefinition(
            key="buffer_charge",
            translation_key="buffer_state_of_charge",
            icon="mdi:battery-heart-variant",
            native_unit_of_measurement="%",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_BUFFER, "buffer_charge")),
        ),
        SensorDefinition(
            key="buffer_capacity",
            translation_key="buffer_volume",
            icon="mdi:storage-tank",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d: to_float(d.value(TYPE_BUFFER, "capacity")),
        ),
        SensorDefinition(
            key="buffer_temp_top",
            translation_key="buffer_top_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_BUFFER, "buffer_temperature_top")),
        ),
        SensorDefinition(
            key="buffer_temp_center",
            translation_key="buffer_middle_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_BUFFER, "buffer_temperature_center")),
        ),
        SensorDefinition(
            key="buffer_temp_bottom",
            translation_key="buffer_bottom_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_BUFFER, "buffer_temperature_bottom")),
        ),
    ]


def boiler_sensors(num: int) -> list[SensorDefinition]:
    number = str(num)
    return [
        SensorDefinition(
            key=f"boiler{num}_enum_state",
            translation_key="boiler_status",
            translation_placeholders={"number": number},
            icon="mdi:water-boiler",
            device_class=SensorDeviceClass.ENUM,
            options=BOILER_STATES,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d: _enum_state(d, TYPE_BOILER, "state", number, BOILER_STATES),
        ),
        SensorDefinition(
            key=f"boiler{num}_temp_current",
            translation_key="boiler_temperature",
            translation_placeholders={"number": number},
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_BOILER, "boiler_temperature_current", number)),
        ),
        SensorDefinition(
            key=f"boiler{num}_temp_target",
            translation_key="boiler_temperature_target",
            translation_placeholders={"number": number},
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(
                first_defined(
                    d.value(TYPE_BOILER, "boiler_temperature_target", number),
                    d.parameter_value(TYPE_BOILER, "boiler_temperature_target", number),
                )
            ),
        ),
        SensorDefinition(
            key=f"boiler{num}_charge",
            translation_key="boiler_state_of_charge",
            translation_placeholders={"number": number},
            native_unit_of_measurement="%",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_BOILER, "boiler_charge", number)),
        ),
    ]


def controller_sensors(*, include_outdoor: bool) -> list[SensorDefinition]:
    descriptions = [
        SensorDefinition(
            key="controller_source_temp",
            translation_key="controller_source_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_HEATING_CONTROLLER, "source_temperature")),
        ),
        SensorDefinition(
            key="controller_request_temp",
            translation_key="controller_request_temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: to_float(d.value(TYPE_HEATING_CONTROLLER, "request_temperature")),
        ),
    ]
    if include_outdoor:
        descriptions.extend(
            [
                SensorDefinition(
                    key="outdoor_temp",
                    translation_key="outdoor_temperature",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    native_unit_of_measurement="°C",
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=_outdoor_temp,
                ),
                SensorDefinition(
                    key="outdoor_temp_avg",
                    translation_key="outdoor_temperature_average",
                    device_class=SensorDeviceClass.TEMPERATURE,
                    native_unit_of_measurement="°C",
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=_outdoor_temp_avg,
                ),
            ]
        )
    return descriptions


def heating_circuit_sensors(widget_type: str, num: int) -> list[SensorDefinition]:
    number = str(num)
    prefix = f"hc{num}"

    def value(field: str) -> Callable[[InstallationState], float | None]:
        return lambda d: to_float(d.value(widget_type, field, number))

    return [
        SensorDefinition(
            key=f"{prefix}_enum_state",
            translation_key="circuit_status",
            translation_placeholders={"number": number},
            icon="mdi:radiator",
            device_class=SensorDeviceClass.ENUM,
            options=CIRCUIT_STATES,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d: _enum_state(d, widget_type, "state", number, CIRCUIT_STATES),
        ),
        SensorDefinition(
            key=f"{prefix}_circuit_mode",
            translation_key="circuit_operating_mode",
            translation_placeholders={"number": number},
            icon="mdi:cog",
            device_class=SensorDeviceClass.ENUM,
            options=CIRCUIT_MODES,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d: _circuit_mode(d, widget_type, number),
        ),
        SensorDefinition(
            key=f"{prefix}_flow_temp_current",
            translation_key="circuit_flow_temperature",
            translation_placeholders={"number": number},
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=value("flow_temperature_current"),
        ),
        SensorDefinition(
            key=f"{prefix}_flow_temp_target",
            translation_key="circuit_flow_temperature_target",
            translation_placeholders={"number": number},
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=value("flow_temperature_target"),
        ),
        SensorDefinition(
            key=f"{prefix}_room_temp_target",
            translation_key="circuit_room_temperature_target",
            translation_placeholders={"number": number},
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=value("room_temperature_target"),
        ),
        SensorDefinition(
            key=f"{prefix}_room_temp_current",
            translation_key="circuit_room_temperature",
            translation_placeholders={"number": number},
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement="°C",
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=value("room_temperature_current"),
        ),
    ]


def _measurement_entity_key(measurement: Measurement) -> str:
    return "measure_" + re.sub(r"[^a-zA-Z0-9]+", "_", measurement.key).strip("_")


def measurement_sensor(measurement: Measurement) -> SensorDefinition:
    def read(data: InstallationState) -> float | None:
        for item in data.measurements:
            if item.key == measurement.key:
                return to_float(item.value)
        return None

    return SensorDefinition(
        key=_measurement_entity_key(measurement),
        name=measurement.name,
        native_unit_of_measurement=measurement.unit,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=read,
    )


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def _is_supported(data: InstallationState, description: SensorDefinition) -> bool:
    """Skip optional sensors when the installation exposes no value."""
    if description.key == "heater_temp_target" or description.key.endswith("_room_temp_current"):
        return description.value_fn is not None and description.value_fn(data) is not None
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: CloudCoordinator = entry.runtime_data.coordinator
    data = coordinator.data
    overrides = parse_field_overrides(entry.options.get(CONF_FIELD_OVERRIDES))
    entities: list[CloudSensor] = []

    if data is None:
        async_add_entities([])
        return

    if data.widget(TYPE_HEATER) is not None:
        for description in heater_sensors():
            if _is_supported(data, description) or description.key in overrides:
                entities.append(
                    CloudSensor(coordinator, entry, description, overrides.get(description.key))
                )

    if data.widget(TYPE_BUFFER) is not None:
        for description in buffer_sensors():
            entities.append(
                CloudSensor(coordinator, entry, description, overrides.get(description.key))
            )

    if data.widget(TYPE_HEATING_CONTROLLER) is not None:
        include_outdoor = data.widget(TYPE_HEATER) is None
        for description in controller_sensors(include_outdoor=include_outdoor):
            entities.append(
                CloudSensor(coordinator, entry, description, overrides.get(description.key))
            )

    seen_boilers: set[int] = set()
    for widget in data.boilers():
        number = normalize_widget_number(widget.number, default=1)
        if number is None or number in seen_boilers:
            continue
        seen_boilers.add(number)
        for description in boiler_sensors(number):
            entities.append(
                CloudSensor(coordinator, entry, description, overrides.get(description.key))
            )

    seen_circuits: set[int] = set()
    for widget in data.heating_circuits():
        number = normalize_widget_number(widget.number)
        if number is None or number in seen_circuits:
            continue
        seen_circuits.add(number)
        for description in heating_circuit_sensors(widget.type, number):
            if _is_supported(data, description) or description.key in overrides:
                entities.append(
                    CloudSensor(coordinator, entry, description, overrides.get(description.key))
                )

    for measurement in data.measurements:
        description = measurement_sensor(measurement)
        entities.append(CloudSensor(coordinator, entry, description, None))

    async_add_entities(entities)


class CloudSensor(CloudEntity, SensorEntity):
    """A sensor entity backed by a widget value or measurement channel."""

    entity_description: SensorDefinition

    def __init__(
        self,
        coordinator: CloudCoordinator,
        entry: ConfigEntry,
        description: SensorDefinition,
        override: dict[str, str] | None,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._description = description
        self._override = override

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if self._override:
            value = read_override(data, self._override)
            if isinstance(value, str):
                return to_str(value)
            return to_float(value)
        if self._description.value_fn is None:
            return None
        return self._description.value_fn(data) if data else None
