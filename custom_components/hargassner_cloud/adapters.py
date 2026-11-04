"""Type coercion helpers for values returned by the Hargassner Cloud API."""

from __future__ import annotations

import math
import re
from typing import Any

_DECIMAL_PATTERN = re.compile(r"^[-+]?\d*(?:[.,]\d+)?$")


def _canonical_number_string(value: str) -> str:
    """Normalize a localized number string such as ``"1.234,5"``."""
    normalized = value.strip().replace(" ", "")
    normalized = normalized.replace(".", "").replace(",", ".")
    return normalized


def to_float(value: Any) -> float | None:
    """Return ``value`` as a finite float, or ``None`` when not numeric."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return None if math.isnan(result) or math.isinf(result) else result
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in {"", "nan", "null", "none", "-"}:
            return None
        candidate = text.replace(" ", "")
        if not _DECIMAL_PATTERN.match(candidate):
            candidate = _canonical_number_string(text)
        try:
            result = float(candidate)
        except ValueError:
            return None
        return None if math.isnan(result) or math.isinf(result) else result
    return None


def to_int(value: Any) -> int | None:
    """Return ``value`` rounded to the nearest integer, or ``None``."""
    result = to_float(value)
    return None if result is None else round(result)


def to_bool(value: Any) -> bool | None:
    """Return ``value`` as a bool, or ``None`` when it is not a clear boolean."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "on", "1", "yes", "y", "active", "enabled"}:
            return True
        if text in {"false", "off", "0", "no", "n", "inactive", "disabled"}:
            return False
    return None


def to_str(value: Any) -> str | None:
    """Return ``value`` as a string, or ``None``."""
    if value is None:
        return None
    return str(value)
