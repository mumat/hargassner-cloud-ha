from __future__ import annotations

import asyncio
from types import SimpleNamespace

from custom_components.hargassner_cloud.diagnostics import (
    async_get_config_entry_diagnostics,
)

RAW = {
    "data": [
        {
            "widget": "HEATER",
            "values": {
                "temperature": 55,
                "name": "Private heater",
                "device_type": "NanoPK",
            },
            "parameters": {"program": {"resource": "/x", "value": "PROGRAM_OFF"}},
            "actions": {"force_charging": {"resource": "/y"}},
        }
    ],
    "meta": {"online_state": True},
}


def test_diagnostics_redacts_entry_and_payload() -> None:
    coordinator = SimpleNamespace(data=SimpleNamespace(raw=RAW), last_update_success=True)
    client = SimpleNamespace(
        diagnostics={
            "phase": "widgets",
            "outcome": "success",
            "credential_source": "discovered",
        }
    )
    entry = SimpleNamespace(
        data={"username": "user@example.test", "password": "secret"},
        options={"area": "Private room"},
        runtime_data=SimpleNamespace(
            coordinator=coordinator,
            client=client,
            device_metadata={"software_version": "V1"},
        ),
    )

    result = asyncio.run(async_get_config_entry_diagnostics(None, entry))  # type: ignore[arg-type]
    rendered = repr(result)

    assert "user@example.test" not in rendered
    assert "secret" not in rendered
    assert "Private heater" not in rendered
    assert "Private room" not in rendered
    assert result["payload_shape"]["device"] == {
        "type": "NanoPK",
        "software_version": "V1",
    }
    assert result["payload_shape"]["widgets"][0]["values"]["temperature"] == "int"
    assert result["payload_shape"]["widgets"][0]["parameters"] == ["program"]
    assert result["api"]["phase"] == "widgets"


def test_diagnostics_without_runtime_data() -> None:
    entry = SimpleNamespace(
        data={"username": "user@example.test", "password": "secret"},
        options={},
        runtime_data=None,
    )
    result = asyncio.run(async_get_config_entry_diagnostics(None, entry))  # type: ignore[arg-type]
    assert "secret" not in repr(result)
    assert result["api"]["outcome"] == "not_loaded"
