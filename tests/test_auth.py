from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from custom_components.hargassner_cloud.auth import (
    fetch_client_credentials,
    parse_client_credentials,
)
from custom_components.hargassner_cloud.exceptions import CloudMaintenanceError
from tests.fakes import FakeResponse, FakeSession

BASE = "https://example.test"


def discover(session: FakeSession) -> tuple[str, str] | None:
    return asyncio.run(fetch_client_credentials(cast(Any, session), BASE))


def test_extract_from_login_call_site() -> None:
    bundle = (
        'const t="wrong-id",a="wrong-secret",ra="7",ps="rotated-secret";'
        "const api={login(i,e,t,a){return post({client_id:t,client_secret:a})}};"
        "class auth{static login(e,t){return api.login(e,t,ra,ps)}}"
    )
    assert parse_client_credentials(bundle) == ("7", "rotated-secret")


def test_extract_from_anchor() -> None:
    bundle = 'const aa="7",bb="secret";request({client_id:aa,client_secret:bb})'
    assert parse_client_credentials(bundle) == ("7", "secret")


def test_extract_legacy() -> None:
    assert parse_client_credentials('o="2",n="legacy-secret"') == (
        "2",
        "legacy-secret",
    )


def test_extract_missing() -> None:
    assert parse_client_credentials("const nothing = 1;") is None


def test_discovery_via_manifest() -> None:
    bundle = 'const aa="1",bb="secret";request({client_id:aa,client_secret:bb})'
    session = FakeSession(
        gets=[
            FakeResponse(200, {"app.js": {"file": "assets/app-x.js", "isEntry": True}}),
            FakeResponse(200, text=bundle),
        ]
    )
    result = discover(session)
    assert result == ("1", "secret")
    assert session.get_calls[1][0] == f"{BASE}/build/assets/app-x.js"


def test_discovery_via_login_page() -> None:
    html = '<script type="module" src="/build/assets/app-test.js"></script>'
    bundle = 'const aa="9",bb="page-secret";request({client_id:aa,client_secret:bb})'
    session = FakeSession(
        gets=[
            FakeResponse(404),
            FakeResponse(200, text=html),
            FakeResponse(200, text=bundle),
        ]
    )
    result = discover(session)
    assert result == ("9", "page-secret")


def test_discovery_detects_maintenance() -> None:
    html = "<html><title>Hargassner | Wartungsarbeiten</title></html>"
    session = FakeSession(gets=[FakeResponse(404), FakeResponse(200, text=html)])
    with pytest.raises(CloudMaintenanceError):
        discover(session)


def test_discovery_returns_none_when_nothing_found() -> None:
    session = FakeSession(
        gets=[FakeResponse(404), FakeResponse(200, text="<html></html>"), FakeResponse(404)]
    )
    assert discover(session) is None
