from __future__ import annotations

import math

import pytest

from custom_components.hargassner_cloud.adapters import (
    to_bool,
    to_float,
    to_int,
    to_str,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("12,5", 12.5),
        ("1.234,5", 1234.5),
        (-2, -2.0),
        (math.nan, None),
        (math.inf, None),
        ("invalid", None),
        (True, None),
    ],
)
def test_to_float(value: object, expected: float | None) -> None:
    assert to_float(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1.6, 2), ("2,4", 2), (None, None), ("invalid", None)],
)
def test_to_int(value: object, expected: int | None) -> None:
    assert to_int(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (0, False),
        (1, True),
        ("yes", True),
        ("off", False),
        ("unknown", None),
    ],
)
def test_to_bool(value: object, expected: bool | None) -> None:
    assert to_bool(value) is expected


def test_to_str() -> None:
    assert to_str(42) == "42"
    assert to_str(None) is None
