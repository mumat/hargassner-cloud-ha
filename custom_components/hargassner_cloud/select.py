"""Select entities (writable enum parameters).

Options are exposed as stable lowercase keys and translated for display via the
entity's ``state`` translations. The key sent to the API is the original option
value, so automations keep working even when the label changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_EXPOSE_ALL_PARAMETERS,
    TYPE_BUFFER,
    TYPE_HEATER,
)
from .coordinator import CloudCoordinator
from .entity import CloudEntity
from .helpers import parameter_kind, normalize_widget_number
from .models import InstallationState, CloudParameter, CloudWidget


def option_key(api_option: object, prefixes: tuple[str, ...]) -> str:
    """Turn an API option into a stable lowercase key.

    A matching enum prefix (for example ``MODE_``) is removed first so the key
    matches the shared state vocabulary used by the sensors.
    """
    text = str(api_option)
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.lower()


@dataclass(frozen=True, kw_only=True)
class SelectDefinition(SelectEntityDescription):
    """Describes a writable enum parameter."""

    widget_type: str
    widget_number: str | None = None
    param_key: str = ""
    option_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SelectTemplate:
    key: str
    translation_key: str
    widget_type: str
    param_key: str
    widget_number: str | None = None
    placeholders: dict[str, str] | None = None
    icon: str | None = None
    option_prefixes: tuple[str, ...] = ()


def _templates(data: InstallationState) -> list[_SelectTemplate]:
    specs = [
        _SelectTemplate(
            key="heater_program",
            translation_key="heater_operation",
            widget_type=TYPE_HEATER,
            param_key="program",
            icon="mdi:fire",
            option_prefixes=("PROGRAM_",),
        ),
        _SelectTemplate(
            key="solar_mode",
            translation_key="solar_operating_mode",
            widget_type=TYPE_BUFFER,
            param_key="solar_mode_active",
            icon="mdi:white-balance-sunny",
            option_prefixes=("SOLAR_MODE_",),
        ),
    ]

    seen: set[int] = set()
    for circuit in data.heating_circuits():
        number = normalize_widget_number(circuit.number)
        if number is None or number in seen:
            continue
        seen.add(number)
        for param_key, translation_key, icon, prefixes in (
            ("mode", "circuit_operating_mode", "mdi:cog", ("MODE_",)),
            ("bathroom_heating", "bathroom_boost", "mdi:shower", ("BATHROOM_HEATING_",)),
            ("pool_heating", "pool_boost", "mdi:pool", ("POOL_HEATING_",)),
        ):
            specs.append(
                _SelectTemplate(
                    key=f"hc{number}_{param_key}",
                    translation_key=translation_key,
                    widget_type=circuit.type,
                    widget_number=str(number),
                    param_key=param_key,
                    placeholders={"number": str(number)},
                    icon=icon,
                    option_prefixes=prefixes,
                )
            )
    return specs


def _option_keys(
    parameter: CloudParameter, prefixes: tuple[str, ...]
) -> list[str]:
    return [option_key(option, prefixes) for option in (parameter.options or [])]


def _description(spec: _SelectTemplate, parameter: CloudParameter) -> SelectDefinition:
    return SelectDefinition(
        key=spec.key,
        translation_key=spec.translation_key,
        translation_placeholders=spec.placeholders,
        widget_type=spec.widget_type,
        widget_number=spec.widget_number,
        param_key=spec.param_key,
        icon=spec.icon,
        entity_category=EntityCategory.CONFIG,
        option_prefixes=spec.option_prefixes,
        options=_option_keys(parameter, spec.option_prefixes),
    )


def _generic_definition(
    widget: CloudWidget, parameter: CloudParameter
) -> SelectDefinition:
    return SelectDefinition(
        key=f"param_{widget.key}_{parameter.key}",
        name=f"{widget.name} {parameter.key.replace('_', ' ').title()}",
        widget_type=widget.type,
        widget_number=widget.number,
        param_key=parameter.key,
        entity_category=EntityCategory.CONFIG,
        options=_option_keys(parameter, ()),
    )


def build_definitions(
    data: InstallationState, expose_all: bool
) -> list[SelectDefinition]:
    descriptions: list[SelectDefinition] = []
    covered: set[tuple[str, str | None, str]] = set()

    for spec in _templates(data):
        widget = data.widget(spec.widget_type, spec.widget_number)
        parameter = widget.parameter(spec.param_key) if widget else None
        if parameter is None or not parameter.writable or not parameter.options:
            continue
        descriptions.append(_description(spec, parameter))
        covered.add((spec.widget_type, spec.widget_number, spec.param_key))

    if expose_all:
        for widget in data.widgets:
            for key, parameter in widget.parameters.items():
                if (widget.type, widget.number, key) in covered:
                    continue
                if parameter_kind(parameter) == "select":
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
        CloudSelect(coordinator, entry, description)
        for description in build_definitions(data, expose_all)
    ]
    async_add_entities(entities)


class CloudSelect(CloudEntity, SelectEntity):
    """A writable enum parameter."""

    entity_description: SelectDefinition

    def __init__(
        self,
        coordinator: CloudCoordinator,
        entry: ConfigEntry,
        description: SelectDefinition,
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
    def _prefixes(self) -> tuple[str, ...]:
        return self.entity_description.option_prefixes

    @property
    def options(self) -> list[str]:
        parameter = self._parameter
        if parameter is None or not parameter.options:
            return []
        return [option_key(option, self._prefixes) for option in parameter.options]

    @property
    def available(self) -> bool:
        parameter = self._parameter
        return super().available and parameter is not None and parameter.writable

    @property
    def current_option(self) -> str | None:
        parameter = self._parameter
        if parameter is None or parameter.value is None:
            return None
        key = option_key(parameter.value, self._prefixes)
        return key if key in self.options else None

    async def async_select_option(self, option: str) -> None:
        parameter = self._parameter
        if parameter is None or not parameter.resource:
            raise HomeAssistantError(f"{self.entity_id}: parameter is not writable")
        api_value = option
        for candidate in parameter.options or []:
            if option_key(candidate, self._prefixes) == option:
                api_value = candidate
                break
        await self.coordinator.client.write_parameter(parameter.resource, api_value)
        await self.coordinator.async_request_refresh()
