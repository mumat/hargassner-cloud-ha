from __future__ import annotations

from custom_components.hargassner_cloud.models import (
    InstallationState,
    parse_state,
)

PAYLOAD = {
    "data": [
        {
            "widget": "HEATER",
            "values": {
                "name": "My heater",
                "device_type": "NanoPK",
                "state": "STATE_ON",
                "heater_temperature_current": 72.0,
            },
            "parameters": {"program": {"value": "PROGRAM_AUTOMATIC", "resource": "/p"}},
            "actions": {"start_ignition": {"resource": "/a", "disabled": False}},
        },
        {
            "widget": "BOILER",
            "number": 1,
            "values": {"boiler_temperature_current": 55},
        },
        {
            "widget": "HEATING_CIRCUIT_RADIATOR",
            "number": "2",
            "values": {"room_temperature_current": 21.5},
            "parameters": {"mode": {"value": "MODE_AUTOMATIC", "resource": "/m"}},
        },
    ],
    "meta": {"online_state": False},
}


def make_data() -> InstallationState:
    return InstallationState(widgets=parse_state(PAYLOAD), meta=PAYLOAD["meta"])


def test_parse_state() -> None:
    widgets = parse_state(PAYLOAD)
    assert [widget.type for widget in widgets] == [
        "HEATER",
        "BOILER",
        "HEATING_CIRCUIT_RADIATOR",
    ]
    heater = widgets[0]
    assert heater.number is None
    assert heater.parameter("program").resource == "/p"
    assert heater.action("start_ignition").available is True


def test_lookups() -> None:
    data = make_data()
    assert data.value("HEATER", "heater_temperature_current") == 72.0
    assert data.value("BOILER", "boiler_temperature_current", "1") == 55
    assert data.parameter_value("HEATING_CIRCUIT_RADIATOR", "mode", "2") == "MODE_AUTOMATIC"
    assert data.widget("MISSING") is None
    assert data.widget("BOILER", "1") is not None
    assert data.widget("BOILER", "9") is None


def test_derived_properties() -> None:
    data = make_data()
    assert data.device_name == "My heater"
    assert data.device_model == "NanoPK"
    assert data.online is False
    assert [widget.type for widget in data.heating_circuits()] == [
        "HEATING_CIRCUIT_RADIATOR"
    ]
    assert [widget.type for widget in data.boilers()] == ["BOILER"]


def test_widget_key() -> None:
    data = make_data()
    assert data.widget("BOILER", "1").key == "boiler_1"
    assert data.widget("HEATER").key == "heater"
