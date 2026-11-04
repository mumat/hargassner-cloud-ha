from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from custom_components.hargassner_cloud import api as api_module
from custom_components.hargassner_cloud.api import CloudApiClient
from custom_components.hargassner_cloud.exceptions import (
    CloudAuthError,
    CloudClientCredentialsError,
)
from tests.fakes import FakeResponse, FakeSession

BASE = "https://example.test"


def make_client(session: FakeSession, **kwargs: Any) -> CloudApiClient:
    return CloudApiClient(
        session,  # type: ignore[arg-type]
        BASE,
        "user@example.test",
        "password",
        "42",
        kwargs.get("client_id", "1"),
        kwargs.get("client_secret", "secret"),
    )


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def patch_discovery(monkeypatch: pytest.MonkeyPatch, result: tuple[str, str] | None) -> None:
    async def _discover(_session: Any, _base: str) -> tuple[str, str] | None:
        return result

    monkeypatch.setattr(
        api_module, "fetch_client_credentials", _discover
    )


def give_token(client: CloudApiClient) -> None:
    client._access_token = "token"
    client._expires_at = time.monotonic() + 1000


def test_login_success_with_stored_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_discovery(monkeypatch, None)
    session = FakeSession(posts=[FakeResponse(200, {"access_token": "t", "expires_in": 1800})])
    client = make_client(session)

    run(client.authenticate())

    assert client._access_token == "t"
    assert client.diagnostics["credential_source"] == "stored"
    assert session.post_calls[0][0] == f"{BASE}/api/auth/login"
    assert session.post_calls[0][1]["json"]["client_id"] == "1"


def test_login_uses_discovered_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_discovery(monkeypatch, ("7", "rotated"))
    session = FakeSession(posts=[FakeResponse(200, {"data": {"access_token": "t"}})])
    client = make_client(session)

    run(client.authenticate())

    assert client._access_token == "t"
    assert client.diagnostics["credential_source"] == "discovered"
    assert session.post_calls[0][1]["json"]["client_id"] == "7"
    assert session.post_calls[0][1]["json"]["client_secret"] == "rotated"


def test_login_rejects_bad_password(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_discovery(monkeypatch, ("7", "rotated"))
    session = FakeSession(posts=[FakeResponse(401)])
    client = make_client(session)

    with pytest.raises(CloudAuthError):
        run(client.authenticate())


def test_login_reports_undiscoverable_client_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_discovery(monkeypatch, None)
    session = FakeSession(posts=[FakeResponse(401)])
    client = make_client(session)

    with pytest.raises(CloudClientCredentialsError):
        run(client.authenticate())


def test_refresh_token(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_discovery(monkeypatch, None)
    session = FakeSession(posts=[FakeResponse(200, {"access_token": "new", "expires_in": 1800})])
    client = make_client(session)
    client._refresh_token = "r"
    client._access_token = None
    client._expires_at = 0.0

    run(client._ensure_token())

    assert client._access_token == "new"
    assert session.post_calls[0][0] == f"{BASE}/api/auth/refresh"


def test_widgets_retry_same_endpoint_after_401(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_discovery(monkeypatch, None)
    session = FakeSession(
        requests=[FakeResponse(401), FakeResponse(200, {"data": []})],
        posts=[FakeResponse(200, {"access_token": "t", "expires_in": 1800})],
    )
    client = make_client(session)
    give_token(client)

    result = run(client.fetch_widgets())

    assert result == {"data": []}
    assert len(session.request_calls) == 2
    assert session.request_calls[0][1] == session.request_calls[1][1]


def test_widgets_fallback_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_discovery(monkeypatch, None)
    session = FakeSession(
        requests=[
            FakeResponse(404),
            FakeResponse(200, {"data": [{"widget": "HEATER"}]}),
        ]
    )
    client = make_client(session)
    give_token(client)

    result = run(client.fetch_widgets())

    assert result == {"data": [{"widget": "HEATER"}]}
    assert "installationId" in session.request_calls[1][2]["params"]


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"id": 42, "name": "Home"}]},
        {"installations": [{"id": "42", "name": "Home"}]},
        [{"id": 42, "name": "Home"}],
    ],
)
def test_parse_installations(payload: object) -> None:
    assert CloudApiClient._installations_from_payload(payload) == [
        {"id": "42", "name": "Home"}
    ]


def test_parse_devices() -> None:
    payload = {
        "data": {
            "devices": [
                {
                    "id": 5,
                    "serial_number": "private",
                    "software": {"version_code": "V1"},
                    "io_firmware_version": "IO_2",
                }
            ]
        }
    }
    assert CloudApiClient._devices_from_payload(payload) == [
        {"id": "5", "software_version": "V1", "io_firmware_version": "IO_2"}
    ]


def test_latest_measurements_picks_newest_values(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_discovery(monkeypatch, None)
    session = FakeSession(
        requests=[
            FakeResponse(
                200,
                {"data": [{"values": {"1": 5}}, {"values": {"1": None, "2": 7}}]},
            )
        ]
    )
    client = make_client(session)
    give_token(client)

    result = run(client._latest_samples("d", ["1", "2"]))

    assert result == {"1": 5, "2": 7}
