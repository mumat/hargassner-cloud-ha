from __future__ import annotations

import json
from pathlib import Path

BASE = Path("custom_components/hargassner_cloud")


def _keys(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return set()
    result: set[str] = set()
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        result.add(path)
        result.update(_keys(child, path))
    return result


def _load(name: str) -> dict:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def test_english_matches_strings() -> None:
    assert _load("strings.json") == _load("translations/en.json")


def test_german_keys_match_english() -> None:
    strings = _load("strings.json")
    german = _load("translations/de.json")
    for section in ("config", "options", "entity", "issues"):
        assert _keys(strings[section]) == _keys(german[section]), section
