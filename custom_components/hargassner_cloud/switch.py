"""Switch entities (writable boolean parameters)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .adapters import to_bool
from .coordinator import CloudCoordinator
from .entity import CloudEntity
from .helpers import parameter_kind
from .models import CloudParameter, CloudWidget, InstallationState


@dataclass(frozen=True, kw_only=True)
class SwitchDefinition(SwitchEntityDescription):
    """Describes a writable boolean parameter."""

    widget_type: str
    widget_number: str | None = None
    param_key: str = ""


def _description(widget: CloudWidget, parameter: CloudParameter) -> SwitchDefinition:
    return SwitchDefinition(
        key=f"param_{widget.key}_{parameter.key}",
        name=f"{widget.name} {parameter.key.replace('_', ' ').title()}",
        widget_type=widget.type,
        widget_number=widget.number,
        param_key=parameter.key,
        entity_category=EntityCategory.CONFIG,
    )


def build_definitions(data: InstallationState) -> list[SwitchDefinition]:
    descriptions: list[SwitchDefinition] = []
    for widget in data.widgets:
        for parameter in widget.parameters.values():
            if parameter_kind(parameter) == "switch":
                descriptions.append(_description(widget, parameter))
    return descriptions


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: CloudCoordinator = entry.runtime_data.coordinator
    data = coordinator.data
    if data is None:
        async_add_entities([])
        return
    entities = [
        CloudSwitch(coordinator, entry, description) for description in build_definitions(data)
    ]
    async_add_entities(entities)


class CloudSwitch(CloudEntity, SwitchEntity):
    """A writable boolean parameter."""

    entity_description: SwitchDefinition

    def __init__(
        self,
        coordinator: CloudCoordinator,
        entry: ConfigEntry,
        description: SwitchDefinition,
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
    def is_on(self) -> bool | None:
        parameter = self._parameter
        return to_bool(parameter.value) if parameter else None

    async def _write(self, value: bool) -> None:
        parameter = self._parameter
        if parameter is None or not parameter.resource:
            raise HomeAssistantError(f"{self.entity_id}: parameter is not writable")
        await self.coordinator.client.write_parameter(parameter.resource, value)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._write(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._write(False)
