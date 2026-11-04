"""Shared fake aiohttp objects for tests."""

from __future__ import annotations

import json
from typing import Any


class FakeResponse:
    """Minimal async-context-manager response."""

    def __init__(
        self,
        status: int,
        payload: Any = None,
        text: str | None = None,
    ) -> None:
        self.status = status
        self._payload = payload if payload is not None else {}
        if text is not None:
            self._text = text
        elif payload is not None:
            self._text = json.dumps(payload)
        else:
            self._text = ""

    async def json(self, content_type: str | None = None) -> Any:
        return self._payload

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeSession:
    """Queue-based fake session recording calls."""

    def __init__(
        self,
        *,
        posts: list[FakeResponse] | None = None,
        gets: list[FakeResponse] | None = None,
        requests: list[FakeResponse] | None = None,
    ) -> None:
        self._posts = list(posts or [])
        self._gets = list(gets or [])
        self._requests = list(requests or [])
        self.post_calls: list[tuple[str, dict[str, Any]]] = []
        self.get_calls: list[tuple[str, dict[str, Any]]] = []
        self.request_calls: list[tuple[str, str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.post_calls.append((url, kwargs))
        return self._posts.pop(0)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.get_calls.append((url, kwargs))
        return self._gets.pop(0)

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.request_calls.append((method, url, kwargs))
        return self._requests.pop(0)
