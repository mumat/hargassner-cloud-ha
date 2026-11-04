from __future__ import annotations

from custom_components.hargassner_cloud.helpers import (
    first_defined,
    normalize_enum,
    normalize_widget_number,
    parameter_kind,
    parse_field_overrides,
)
from custom_components.hargassner_cloud.models import CloudParameter


def test_normalize_widget_number() -> None:
    assert normalize_widget_number("3") == 3
    assert normalize_widget_number(4) == 4
    assert normalize_widget_number(None, default=2) == 2
    assert normalize_widget_number(0) is None
    assert normalize_widget_number("x") is None
    assert normalize_widget_number(True) is None


def test_first_defined_keeps_falsey_values() -> None:
    assert first_defined(None, 0, 1) == 0
    assert first_defined(None, False, True) is False
    assert first_defined(None, None) is None


def test_normalize_enum() -> None:
    options = ["off", "on", "heating"]
    assert normalize_enum("STATE_ON", options, "STATE") == "on"
    assert normalize_enum("STATE_HEATING", options, "STATE") == "heating"
    assert normalize_enum("STATE_UNKNOWN", options, "STATE") is None
    assert normalize_enum(None, options, "STATE") is None


def test_parameter_kind() -> None:
    assert parameter_kind(CloudParameter(key="m", resource="/x", options=["A"])) == "select"
    assert parameter_kind(CloudParameter(key="b", resource="/x", value=True)) == "switch"
    assert (
        parameter_kind(CloudParameter(key="n", resource="/x", minimum=0, maximum=10))
        == "number"
    )
    assert parameter_kind(CloudParameter(key="n", resource="/x", value="text")) is None
    assert parameter_kind(CloudParameter(key="n", value=True)) is None


def test_parse_field_overrides() -> None:
    assert parse_field_overrides(None) == {}
    assert parse_field_overrides("") == {}
    assert parse_field_overrides("not-json") == {}
    assert parse_field_overrides('{"a": {"widget": "HEATER", "field": "x", "extra": "y"}}') == {
        "a": {"widget": "HEATER", "field": "x"}
    }
    assert parse_field_overrides('{"a": {"widget": "HEATER"}}') == {}
