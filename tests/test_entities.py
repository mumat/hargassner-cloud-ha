from __future__ import annotations

from typing import Any

from custom_components.hargassner_cloud import binary_sensor as binary_platform
from custom_components.hargassner_cloud import button as button_platform
from custom_components.hargassner_cloud import climate as climate_platform
from custom_components.hargassner_cloud import number as number_platform
from custom_components.hargassner_cloud import select as select_platform
from custom_components.hargassner_cloud import sensor as sensor_platform
from custom_components.hargassner_cloud import switch as switch_platform
from custom_components.hargassner_cloud.models import InstallationState, parse_state

PAYLOAD: dict[str, Any] = {
    "data": [
        {
            "widget": "HEATER",
            "values": {
                "name": "NanoPK",
                "device_type": "NanoPK",
                "state": "STATE_ON",
                "smoke_temperature": 101.5,
                "heater_temperature_current": 72.0,
                "heater_temperature_target": 75,
                "outdoor_temperature": 8.5,
                "outdoor_temperature_average": 7.0,
                "efficiency": 91,
                "heater_exhaust_guard": True,
                "fuel_stock": 1200,
            },
            "parameters": {
                "program": {
                    "value": "PROGRAM_AUTOMATIC",
                    "resource": "/program",
                    "options": ["PROGRAM_OFF", "PROGRAM_AUTOMATIC"],
                },
                "fuel_stock": {
                    "value": 1200,
                    "resource": "/fuel",
                    "min": 0,
                    "max": 7874,
                    "step": 1,
                },
                "extra_number": {"value": 5, "resource": "/en", "min": 0, "max": 10},
                "extra_flag": {"value": True, "resource": "/flag"},
            },
            "actions": {"start_ignition": {"resource": "/ignite"}},
        },
        {
            "widget": "BUFFER",
            "values": {
                "state": "STATE_ON",
                "buffer_charge": 64,
                "buffer_temperature_top": 55,
                "pump_active": True,
            },
            "parameters": {
                "solar_mode_active": {
                    "value": "SOLAR_MODE_OFF",
                    "resource": "/solar",
                    "options": ["SOLAR_MODE_OFF", "SOLAR_MODE_ON"],
                }
            },
            "actions": {"force_charging": {"resource": "/buffer-force", "disabled": True}},
        },
        {
            "widget": "BOILER",
            "number": "1",
            "values": {
                "boiler_temperature_current": 54.5,
                "boiler_temperature_target": 60,
                "boiler_charge": 82,
                "pump_active": False,
            },
            "parameters": {
                "boiler_temperature_target": {
                    "value": 60,
                    "resource": "/boiler-target",
                    "min": 10,
                    "max": 84,
                    "step": 0.5,
                }
            },
            "actions": {"force_charging": {"resource": "/boiler-force", "disabled": False}},
        },
        {
            "widget": "HEATING_CIRCUIT_RADIATOR",
            "number": "1",
            "values": {
                "state": "STATE_HEATING",
                "flow_temperature_current": 31.5,
                "flow_temperature_target": 35,
                "room_temperature_target": 20,
                "room_temperature_current": 21.5,
                "pump_active": False,
                "active": True,
            },
            "parameters": {
                "mode": {
                    "value": "MODE_AUTOMATIC",
                    "resource": "/mode",
                    "options": ["MODE_OFF", "MODE_AUTOMATIC", "MODE_HEATING"],
                },
                "room_temperature_heating": {
                    "value": 21,
                    "resource": "/heat",
                    "min": 10,
                    "max": 30,
                    "step": 0.5,
                },
                "steepness": {
                    "value": 1.2,
                    "resource": "/slope",
                    "min": 0.2,
                    "max": 3.5,
                    "step": 0.05,
                },
            },
        },
        {
            "widget": "HEATING_CIRCUIT_CONTROLLER",
            "values": {
                "source_temperature": 65,
                "request_temperature": 70,
                "outdoor_temperature": 8.5,
                "outdoor_temperature_average": 7.0,
            },
        },
    ],
    "meta": {"online_state": True},
}


def make_data() -> InstallationState:
    return InstallationState(widgets=parse_state(PAYLOAD), meta=PAYLOAD["meta"])


def _values(descriptions, data):
    return {
        description.key: description.value_fn(data)
        for description in descriptions
        if description.value_fn is not None
    }


def test_sensor_values() -> None:
    data = make_data()
    descriptions = [
        *sensor_platform.heater_sensors(),
        *sensor_platform.buffer_sensors(),
        *sensor_platform.boiler_sensors(1),
        *sensor_platform.heating_circuit_sensors("HEATING_CIRCUIT_RADIATOR", 1),
        *sensor_platform.controller_sensors(include_outdoor=False),
    ]
    values = _values(descriptions, data)

    assert values["heater_state"] == "on"
    assert values["heater_program"] == "automatic"
    assert values["heater_smoke_temp"] == 101.5
    assert values["heater_temp_target"] == 75.0
    assert values["outdoor_temp"] == 8.5
    assert values["buffer_charge"] == 64.0
    assert values["boiler1_temp_current"] == 54.5
    assert values["hc1_flow_temp_current"] == 31.5
    assert values["hc1_mode"] == "automatic"
    assert values["controller_source_temp"] == 65.0


def test_binary_descriptions() -> None:
    data = make_data()
    descriptions = binary_platform.build_definitions(data)
    keys = {description.key for description in descriptions}
    assert keys == {
        "cloud_connection",
        "heater_running",
        "exhaust_guard",
        "buffer_pump",
        "buffer_force_charge",
        "boiler1_pump",
        "boiler1_force_charge",
        "hc1_pump",
        "hc1_running",
    }
    values = _values(descriptions, data)
    assert values["cloud_connection"] is True
    assert values["heater_running"] is True
    assert values["exhaust_guard"] is True
    assert values["buffer_force_charge"] is True
    assert values["hc1_running"] is True
    assert values["hc1_pump"] is False


def test_number_descriptions() -> None:
    data = make_data()
    keys = {description.key for description in number_platform.build_definitions(data, True)}
    assert "pellet_stock" in keys
    assert "boiler1_hot_water_temperature" in keys
    assert "hc1_room_temperature_heating" in keys
    assert "hc1_steepness" in keys
    assert "param_heater_extra_number" in keys


def test_select_descriptions() -> None:
    data = make_data()
    descriptions = select_platform.build_definitions(data, False)
    keys = {description.key for description in descriptions}
    assert keys == {"heater_program", "solar_mode", "hc1_mode"}
    program = next(d for d in descriptions if d.key == "heater_program")
    assert program.options == ["off", "automatic"]
    assert program.translation_key == "heater_operation"
    circuit = next(d for d in descriptions if d.key == "hc1_mode")
    assert circuit.options == ["off", "automatic", "heating"]
    assert circuit.option_prefixes == ("MODE_",)


def test_select_option_keys_strip_enum_prefix() -> None:
    from custom_components.hargassner_cloud.select import option_key

    assert option_key("MODE_AUTOMATIC", ("MODE_",)) == "automatic"
    assert option_key("PROGRAM_STOP_FIRING", ("PROGRAM_",)) == "stop_firing"
    assert option_key("SOLAR_MODE_OFF", ("SOLAR_MODE_",)) == "off"
    assert option_key("OFF", ("BATHROOM_HEATING_",)) == "off"
    assert option_key("Something_Custom", ()) == "something_custom"


def test_curated_select_options_are_translated() -> None:
    import json
    from pathlib import Path

    data = make_data()
    select_states = json.loads(
        Path("custom_components/hargassner_cloud/translations/en.json").read_text(encoding="utf-8")
    )["entity"]["select"]
    for description in select_platform.build_definitions(data, False):
        states = select_states.get(description.translation_key, {}).get("state", {})
        for option in description.options or []:
            assert option in states, f"{description.translation_key}.{option} has no label"


def test_switch_descriptions() -> None:
    data = make_data()
    keys = {description.key for description in switch_platform.build_definitions(data)}
    assert keys == {"param_heater_extra_flag"}


def test_button_descriptions() -> None:
    data = make_data()
    descriptions = button_platform.build_definitions(data)
    keys = {description.key for description in descriptions}
    assert "heater_start_ignition" in keys
    assert "boiler_1_force_charging" in keys
    assert "buffer_force_charging" in keys


def test_climate_parameter_selection() -> None:
    data = make_data()
    widget = data.widget("HEATING_CIRCUIT_RADIATOR", "1")
    assert widget is not None
    setpoint = climate_platform._find_setpoint(widget)
    mode = climate_platform._find_circuit_mode(widget)
    assert setpoint is not None and setpoint.key == "room_temperature_heating"
    assert mode is not None and mode.key == "mode"


def test_every_translation_key_is_translated() -> None:
    import json
    from pathlib import Path

    data = make_data()
    translations = json.loads(
        Path("custom_components/hargassner_cloud/translations/en.json").read_text(encoding="utf-8")
    )["entity"]
    groups: dict[str, list[Any]] = {
        "sensor": [
            *sensor_platform.heater_sensors(),
            *sensor_platform.buffer_sensors(),
            *sensor_platform.boiler_sensors(1),
            *sensor_platform.heating_circuit_sensors("HEATING_CIRCUIT_RADIATOR", 1),
            *sensor_platform.controller_sensors(include_outdoor=False),
        ],
        "binary_sensor": binary_platform.build_definitions(data),
        "number": number_platform.build_definitions(data, True),
        "select": select_platform.build_definitions(data, False),
        "button": button_platform.build_definitions(data),
    }
    for platform, descriptions in groups.items():
        for description in descriptions:
            key = description.translation_key
            if key is None:
                continue
            assert key in translations[platform], f"{platform}.{key} is untranslated"
