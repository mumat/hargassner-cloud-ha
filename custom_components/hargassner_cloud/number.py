"""Number entities (writable numeric parameters)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .adapters import to_float
from .const import (
    CONF_EXPOSE_ALL_PARAMETERS,
    TYPE_BOILER,
    TYPE_HEATER,
)
from .coordinator import CloudCoordinator
from .entity import CloudEntity
from .helpers import normalize_widget_number, parameter_kind
from .models import CloudParameter, CloudWidget, InstallationState


@dataclass(frozen=True, kw_only=True)
class NumberDefinition(NumberEntityDescription):
    """Describes a writable numeric parameter."""

    widget_type: str
    widget_number: str | None = None
    param_key: str = ""
    fallback_min: float = 0.0
    fallback_max: float = 100.0
    fallback_step: float = 1.0


@dataclass(frozen=True)
class _NumberTemplate:
    key: str
    translation_key: str
    widget_type: str
    param_key: str
    widget_number: str | None = None
    placeholders: dict[str, str] | None = None
    device_class: NumberDeviceClass | None = None
    unit: str | None = None
    icon: str | None = None
    mode: NumberMode = NumberMode.BOX
    fallback_min: float = 0.0
    fallback_max: float = 100.0
    fallback_step: float = 1.0


def _templates(data: InstallationState) -> list[_NumberTemplate]:
    specs: list[_NumberTemplate] = [
        _NumberTemplate(
            key="pellet_stock",
            translation_key="fuel_stock_level",
            widget_type=TYPE_HEATER,
            param_key="fuel_stock",
            icon="mdi:sack",
            unit="kg",
            fallback_max=32000.0,
        )
    ]

    for boiler in data.boilers():
        number = normalize_widget_number(boiler.number, default=1)
        if number is None:
            continue
        specs.append(
            _NumberTemplate(
                key=f"boiler{number}_hot_water_temperature",
                translation_key="hot_water_target",
                widget_type=TYPE_BOILER,
                widget_number=str(number),
                param_key="boiler_temperature_target",
                placeholders={"number": str(number)},
                device_class=NumberDeviceClass.TEMPERATURE,
                unit="°C",
                fallback_min=10.0,
                fallback_max=84.0,
                fallback_step=0.5,
            )
        )

    circuit_params = (
        (
            "room_temperature_heating",
            "room_setpoint_day",
            NumberDeviceClass.TEMPERATURE,
            "°C",
            10.0,
            30.0,
            0.5,
            NumberMode.BOX,
        ),
        (
            "room_temperature_reduction",
            "room_setpoint_night",
            NumberDeviceClass.TEMPERATURE,
            "°C",
            10.0,
            30.0,
            0.5,
            NumberMode.BOX,
        ),
        (
            "room_temperature_correction",
            "room_offset",
            NumberDeviceClass.TEMPERATURE,
            "°C",
            -3.0,
            3.0,
            0.5,
            NumberMode.BOX,
        ),
        ("steepness", "heating_curve_slope", None, None, 0.2, 3.5, 0.05, NumberMode.SLIDER),
        (
            "deactivation_limit_heating",
            "heating_cutoff",
            NumberDeviceClass.TEMPERATURE,
            "°C",
            -10.0,
            50.0,
            1.0,
            NumberMode.BOX,
        ),
        (
            "deactivation_limit_reduction_day",
            "day_setback_cutoff",
            NumberDeviceClass.TEMPERATURE,
            "°C",
            -40.0,
            50.0,
            1.0,
            NumberMode.BOX,
        ),
        (
            "deactivation_limit_reduction_night",
            "night_setback_cutoff",
            NumberDeviceClass.TEMPERATURE,
            "°C",
            -40.0,
            50.0,
            1.0,
            NumberMode.BOX,
        ),
    )
    seen: set[int] = set()
    for circuit in data.heating_circuits():
        number = normalize_widget_number(circuit.number)
        if number is None or number in seen:
            continue
        seen.add(number)
        for (
            param_key,
            translation_key,
            device_class,
            unit,
            low,
            high,
            step,
            mode,
        ) in circuit_params:
            specs.append(
                _NumberTemplate(
                    key=f"hc{number}_{param_key}",
                    translation_key=translation_key,
                    widget_type=circuit.type,
                    widget_number=str(number),
                    param_key=param_key,
                    placeholders={"number": str(number)},
                    device_class=device_class,
                    unit=unit,
                    icon="mdi:slope-uphill" if param_key == "steepness" else None,
                    mode=mode,
                    fallback_min=low,
                    fallback_max=high,
                    fallback_step=step,
                )
            )
    return specs


def _definition_from_template(spec: _NumberTemplate, parameter: CloudParameter) -> NumberDefinition:
    return NumberDefinition(
        key=spec.key,
        translation_key=spec.translation_key,
        translation_placeholders=spec.placeholders,
        widget_type=spec.widget_type,
        widget_number=spec.widget_number,
        param_key=spec.param_key,
        device_class=spec.device_class,
        native_unit_of_measurement=spec.unit or parameter.unit,
        icon=spec.icon,
        mode=spec.mode,
        native_min_value=parameter.minimum if parameter.minimum is not None else spec.fallback_min,
        native_max_value=parameter.maximum if parameter.maximum is not None else spec.fallback_max,
        native_step=parameter.step if parameter.step else spec.fallback_step,
        fallback_min=spec.fallback_min,
        fallback_max=spec.fallback_max,
        fallback_step=spec.fallback_step,
    )


def _generic_definition(widget: CloudWidget, parameter: CloudParameter) -> NumberDefinition:
    key = f"param_{widget.key}_{parameter.key}"
    name = f"{widget.name} {parameter.key.replace('_', ' ').title()}"
    return NumberDefinition(
        key=key,
        name=name,
        widget_type=widget.type,
        widget_number=widget.number,
        param_key=parameter.key,
        native_unit_of_measurement=parameter.unit,
        native_min_value=parameter.minimum or 0.0,
        native_max_value=parameter.maximum or 100.0,
        native_step=parameter.step or 1.0,
        mode=NumberMode.BOX,
    )


def build_definitions(data: InstallationState, expose_all: bool) -> list[NumberDefinition]:
    descriptions: list[NumberDefinition] = []
    covered: set[tuple[str, str | None, str]] = set()

    for spec in _templates(data):
        widget = data.widget(spec.widget_type, spec.widget_number)
        parameter = widget.parameter(spec.param_key) if widget else None
        if parameter is None or not parameter.writable:
            continue
        descriptions.append(_definition_from_template(spec, parameter))
        covered.add((spec.widget_type, spec.widget_number, spec.param_key))

    if expose_all:
        for widget in data.widgets:
            for key, parameter in widget.parameters.items():
                if (widget.type, widget.number, key) in covered:
                    continue
                if parameter_kind(parameter) == "number":
                    descriptions.append(_generic_definition(widget, parameter))
    return descriptions


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: CloudCoordinator = entry.runtime_data.coordinator
    data = coordinator.data
    if data is None:
        async_add_entities([])
        return
    expose_all = bool(entry.options.get(CONF_EXPOSE_ALL_PARAMETERS))
    entities = [
        CloudNumber(coordinator, entry, description)
        for description in build_definitions(data, expose_all)
    ]
    async_add_entities(entities)


class CloudNumber(CloudEntity, NumberEntity):
    """A writable numeric parameter."""

    entity_description: NumberDefinition

    def __init__(
        self,
        coordinator: CloudCoordinator,
        entry: ConfigEntry,
        description: NumberDefinition,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def _parameter(self) -> CloudParameter | None:
        data = self.coordinator.data
        if data is None:
            return None
        widget = data.widget(
            self.entity_description.widget_type, self.entity_description.widget_number
        )
        return widget.parameter(self.entity_description.param_key) if widget else None

    @property
    def available(self) -> bool:
        parameter = self._parameter
        return super().available and parameter is not None and parameter.writable

    @property
    def native_value(self) -> float | None:
        parameter = self._parameter
        return to_float(parameter.value) if parameter else None

    async def async_set_native_value(self, value: float) -> None:
        parameter = self._parameter
        if parameter is None or not parameter.resource:
            raise HomeAssistantError(f"{self.entity_id}: parameter is not writable")
        await self.coordinator.client.write_parameter(parameter.resource, value)
        await self.coordinator.async_request_refresh()
