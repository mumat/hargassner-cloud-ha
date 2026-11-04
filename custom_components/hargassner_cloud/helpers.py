"""Shared helpers for widget lookup and parameter classification."""

from __future__ import annotations

from typing import Any

from .models import CloudParameter


def normalize_widget_number(value: Any, default: int | None = None) -> int | None:
    """Coerce a widget number to a positive int, or ``None`` when unusable."""
    candidate = value if value is not None else default
    if isinstance(candidate, bool):
        return None
    if not isinstance(candidate, (int, str)):
        return None
    try:
        number = int(candidate)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def first_defined(*values: Any) -> Any:
    """Return the first value that is not ``None`` (keeping falsey values)."""
    for value in values:
        if value is not None:
            return value
    return None


def normalize_enum(value: Any, options: list[str], prefix: str) -> str | None:
    """Normalize an ``PREFIX_*`` API enum into a translation key."""
    from .adapters import to_str

    text = to_str(value)
    if not text or not text.startswith(f"{prefix}_"):
        return None
    normalized = text[len(prefix) + 1 :].lower()
    if normalized not in options:
        return None
    return normalized


def parameter_kind(parameter: CloudParameter) -> str | None:
    """Classify a writable parameter for generic entity exposure.

    Returns ``"select"``, ``"switch"``, ``"number"`` or ``None`` when the
    parameter cannot be exposed safely.
    """
    if not parameter.writable:
        return None
    if parameter.is_enum:
        return "select"
    if parameter.is_boolean:
        return "switch"
    if parameter.is_numeric:
        return "number"
    return None


def parse_field_overrides(raw: str | None) -> dict[str, dict[str, str]]:
    """Parse the field-overrides option into a validated mapping."""
    import json

    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        cleaned = {
            field: str(value[field])
            for field in ("widget", "field", "number")
            if value.get(field) is not None
        }
        if "widget" in cleaned and "field" in cleaned:
            result[str(key)] = cleaned
    return result
