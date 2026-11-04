"""Button entities (one-shot widget actions)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CloudCoordinator
from .entity import CloudEntity
from .models import CloudAction, CloudWidget, InstallationState

# Friendly translation keys for well-known actions.
_KNOWN_ACTIONS = {
    "force_charging": "force_hot_water_charge",
    "confirm_all": "acknowledge_events",
    "start_ignition": "start_ignition",
}


@dataclass(frozen=True, kw_only=True)
class ButtonDefinition(ButtonEntityDescription):
    """Describes a widget action button."""

    widget_type: str
    widget_number: str | None = None
    action_key: str = ""


def _description(widget: CloudWidget, action: CloudAction) -> ButtonDefinition:
    translation_key = _KNOWN_ACTIONS.get(action.key)
    if translation_key:
        return ButtonDefinition(
            key=f"{widget.key}_{action.key}",
            translation_key=translation_key,
            widget_type=widget.type,
            widget_number=widget.number,
            action_key=action.key,
        )
    return ButtonDefinition(
        key=f"action_{widget.key}_{action.key}",
        name=f"{widget.name} {action.key.replace('_', ' ').title()}",
        widget_type=widget.type,
        widget_number=widget.number,
        action_key=action.key,
    )


def build_definitions(data: InstallationState) -> list[ButtonDefinition]:
    descriptions: list[ButtonDefinition] = []
    for widget in data.widgets:
        for action in widget.actions.values():
            if action.resource:
                descriptions.append(_description(widget, action))
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
        CloudButton(coordinator, entry, description) for description in build_definitions(data)
    ]
    async_add_entities(entities)


class CloudButton(CloudEntity, ButtonEntity):
    """A one-shot action on the boiler."""

    entity_description: ButtonDefinition

    def __init__(
        self,
        coordinator: CloudCoordinator,
        entry: ConfigEntry,
        description: ButtonDefinition,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def _action(self) -> CloudAction | None:
        data = self.coordinator.data
        if data is None:
            return None
        widget = data.widget(
            self.entity_description.widget_type, self.entity_description.widget_number
        )
        return widget.action(self.entity_description.action_key) if widget else None

    @property
    def available(self) -> bool:
        action = self._action
        return super().available and action is not None and action.available

    async def async_press(self) -> None:
        action = self._action
        if action is None or not action.resource:
            raise HomeAssistantError(f"{self.entity_id}: no action resource available")
        await self.coordinator.client.run_action(action.resource)
        await self.coordinator.async_request_refresh()
