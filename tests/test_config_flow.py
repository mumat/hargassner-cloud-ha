from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.data_entry_flow import AbortFlow, FlowResultType

from custom_components.hargassner_cloud.config_flow import HargassnerCloudConfigFlow
from custom_components.hargassner_cloud.const import CONF_INSTALLATION
from custom_components.hargassner_cloud.exceptions import (
    CloudAuthError,
    CloudClientCredentialsError,
    CloudConnectionError,
    CloudMaintenanceError,
)

USER_INPUT = {"username": "user@example.test", "password": "password"}


def make_flow(installations: list[dict[str, str]]) -> HargassnerCloudConfigFlow:
    flow = HargassnerCloudConfigFlow()
    flow.hass = MagicMock()
    client = SimpleNamespace(
        authenticate=AsyncMock(),
        fetch_installations=AsyncMock(return_value=installations),
    )
    flow._client = MagicMock(return_value=client)  # type: ignore[method-assign]
    flow.async_set_unique_id = AsyncMock()  # type: ignore[method-assign]
    flow._abort_if_unique_id_configured = MagicMock()  # type: ignore[method-assign]
    return flow


def test_single_installation_is_selected_automatically() -> None:
    flow = make_flow([{"id": "42", "name": "Home"}])
    result = asyncio.run(flow.async_step_user(dict(USER_INPUT)))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home"
    assert result["data"][CONF_INSTALLATION] == "42"


def test_multiple_installations_show_selection() -> None:
    flow = make_flow([{"id": "42", "name": "Home"}, {"id": "84", "name": "Workshop"}])
    result = asyncio.run(flow.async_step_user(dict(USER_INPUT)))
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "installation"

    result = asyncio.run(flow.async_step_installation({CONF_INSTALLATION: "84"}))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_INSTALLATION] == "84"


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (CloudAuthError("bad"), "auth"),
        (CloudClientCredentialsError("rotated"), "web_client_credentials"),
        (CloudMaintenanceError("maintenance"), "maintenance"),
        (CloudConnectionError("offline"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
def test_setup_errors(exception: Exception, error: str) -> None:
    flow = make_flow([])
    flow._client.return_value.authenticate.side_effect = exception  # type: ignore[attr-defined]
    result = asyncio.run(flow.async_step_user(dict(USER_INPUT)))
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


def test_no_installations() -> None:
    flow = make_flow([])
    result = asyncio.run(flow.async_step_user(dict(USER_INPUT)))
    assert result["errors"] == {"base": "no_installations"}


def test_duplicate_installation_is_rejected() -> None:
    flow = make_flow([{"id": "42", "name": "Home"}])
    flow._abort_if_unique_id_configured.side_effect = AbortFlow("already_configured")  # type: ignore[attr-defined]
    with pytest.raises(AbortFlow, match="already_configured"):
        asyncio.run(flow.async_step_user(dict(USER_INPUT)))
