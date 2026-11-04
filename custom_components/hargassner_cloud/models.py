"""Structured data model for the Hargassner Cloud widget response."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import (
    NAME,
    TYPE_HEATER,
    TYPE_HEATING_CIRCUIT,
    TYPE_HEATING_CONTROLLER,
)


def _as_float(value: Any) -> float | None:
    """Return a finite float or ``None`` without importing the adapters module."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


@dataclass(slots=True)
class CloudParameter:
    """A single entry from a widget's ``parameters`` block."""

    key: str
    value: Any = None
    resource: str | None = None
    options: list[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    unit: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def writable(self) -> bool:
        return bool(self.resource)

    @property
    def is_boolean(self) -> bool:
        return isinstance(self.value, bool)

    @property
    def is_numeric(self) -> bool:
        return self.minimum is not None and self.maximum is not None

    @property
    def is_enum(self) -> bool:
        return bool(self.options)


@dataclass(slots=True)
class CloudAction:
    """A single entry from a widget's ``actions`` block."""

    key: str
    resource: str | None = None
    disabled: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return bool(self.resource) and not self.disabled


@dataclass(slots=True)
class CloudWidget:
    """One widget from the ``/widgets`` payload."""

    type: str
    number: str | None
    name: str
    values: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, CloudParameter] = field(default_factory=dict)
    actions: dict[str, CloudAction] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Return a stable, lower-case identifier for this widget instance."""
        base = self.type.lower()
        return f"{base}_{self.number}" if self.number else base

    def value(self, name: str, default: Any = None) -> Any:
        return self.values.get(name, default)

    def parameter(self, key: str) -> CloudParameter | None:
        return self.parameters.get(key)

    def action(self, key: str) -> CloudAction | None:
        return self.actions.get(key)


@dataclass(slots=True)
class Measurement:
    """One channel from the optional measurement-history API."""

    key: str
    name: str
    unit: str | None
    value: Any
    device_id: str
    channel_id: str
    group: str | None = None


@dataclass(slots=True)
class InstallationState:
    """Complete parsed state returned by the coordinator poll."""

    widgets: list[CloudWidget] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    measurements: list[Measurement] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    # -- widget lookup -----------------------------------------------------

    def widget(self, widget_type: str, number: str | int | None = None) -> CloudWidget | None:
        """Return the first widget with the exact type (and number)."""
        for widget in self.widgets:
            if widget.type != widget_type:
                continue
            if number is not None and str(widget.number) != str(number):
                continue
            return widget
        return None

    def widgets_starting_with(
        self, prefix: str, number: str | int | None = None
    ) -> list[CloudWidget]:
        """Return every widget whose type starts with ``prefix``."""
        result = []
        for widget in self.widgets:
            if not widget.type.startswith(prefix):
                continue
            if number is not None and str(widget.number) != str(number):
                continue
            result.append(widget)
        return result

    def heating_circuits(self) -> list[CloudWidget]:
        """Return all heating-circuit widgets except the controller widget."""
        return [
            widget
            for widget in self.widgets
            if widget.type.startswith(f"{TYPE_HEATING_CIRCUIT}_")
            and widget.type != TYPE_HEATING_CONTROLLER
        ]

    def boilers(self) -> list[CloudWidget]:
        return [widget for widget in self.widgets if widget.type == TYPE_BOILER]

    # -- values ------------------------------------------------------------

    def value(
        self,
        widget_type: str,
        name: str,
        number: str | int | None = None,
        default: Any = None,
    ) -> Any:
        widget = self.widget(widget_type, number)
        return widget.value(name, default) if widget else default

    def parameter_value(
        self,
        widget_type: str,
        key: str,
        number: str | int | None = None,
    ) -> Any:
        widget = self.widget(widget_type, number)
        parameter = widget.parameter(key) if widget else None
        return parameter.value if parameter else None

    # -- metadata ----------------------------------------------------------

    @property
    def online(self) -> bool:
        return bool(self.meta.get("online_state", True))

    @property
    def device_name(self) -> str:
        heater = self.widget(TYPE_HEATER)
        if heater and heater.value("name"):
            return str(heater.value("name"))
        return NAME

    @property
    def device_model(self) -> str:
        heater = self.widget(TYPE_HEATER)
        if heater and heater.value("device_type"):
            return str(heater.value("device_type"))
        return "Hargassner"


def parse_state(payload: Any) -> list[CloudWidget]:
    """Parse the raw ``/widgets`` payload into :class:`CloudWidget` objects."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []

    widgets: list[CloudWidget] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        widget_type = str(item.get("widget") or "").strip()
        if not widget_type:
            continue

        values = item.get("values")
        values = values if isinstance(values, dict) else {}

        parameters: dict[str, CloudParameter] = {}
        raw_parameters = item.get("parameters")
        if isinstance(raw_parameters, dict):
            for key, entry in raw_parameters.items():
                if not isinstance(entry, dict):
                    continue
                options = entry.get("options")
                parameters[str(key)] = CloudParameter(
                    key=str(key),
                    value=entry.get("value"),
                    resource=entry.get("resource")
                    if isinstance(entry.get("resource"), str)
                    else None,
                    options=[str(option) for option in options]
                    if isinstance(options, list)
                    else None,
                    minimum=_as_float(entry.get("min")),
                    maximum=_as_float(entry.get("max")),
                    step=_as_float(entry.get("step")),
                    unit=entry.get("unit") if isinstance(entry.get("unit"), str) else None,
                    raw=entry,
                )

        actions: dict[str, CloudAction] = {}
        raw_actions = item.get("actions")
        if isinstance(raw_actions, dict):
            for key, entry in raw_actions.items():
                if not isinstance(entry, dict):
                    continue
                actions[str(key)] = CloudAction(
                    key=str(key),
                    resource=entry.get("resource")
                    if isinstance(entry.get("resource"), str)
                    else None,
                    disabled=entry.get("disabled")
                    if isinstance(entry.get("disabled"), bool)
                    else None,
                    raw=entry,
                )

        number = item.get("number")
        widgets.append(
            CloudWidget(
                type=widget_type,
                number=str(number) if number is not None else None,
                name=str(values.get("name") or widget_type.replace("_", " ").title()),
                values=values,
                parameters=parameters,
                actions=actions,
                raw=item,
            )
        )
    return widgets
