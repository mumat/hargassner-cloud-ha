"""Options flow for the Hargassner Cloud integration."""

from __future__ import annotations

import json

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload

from .const import (
    CONF_AREA,
    CONF_ENABLE_MEASUREMENTS,
    CONF_EXPOSE_ALL_PARAMETERS,
    CONF_FIELD_OVERRIDES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


def _mapping_is_valid(raw: object) -> bool:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return True
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    return all(isinstance(value, dict) for value in data.values())


class HargassnerCloudOptionsFlow(OptionsFlowWithReload):
    """Manage polling, area, mappings and optional entity coverage."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if _mapping_is_valid(user_input.get(CONF_FIELD_OVERRIDES)):
                return self.async_create_entry(title="", data=user_input)
            errors[CONF_FIELD_OVERRIDES] = "invalid_mapping"

        options = self.config_entry.options
        data = self.config_entry.data
        defaults = {
            CONF_SCAN_INTERVAL: options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            CONF_AREA: options.get(CONF_AREA, data.get(CONF_AREA, "")),
            CONF_EXPOSE_ALL_PARAMETERS: options.get(CONF_EXPOSE_ALL_PARAMETERS, False),
            CONF_ENABLE_MEASUREMENTS: options.get(CONF_ENABLE_MEASUREMENTS, False),
            CONF_FIELD_OVERRIDES: options.get(CONF_FIELD_OVERRIDES, ""),
        }
        if user_input is not None:
            defaults.update(user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=defaults[CONF_SCAN_INTERVAL]
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Optional(CONF_AREA, default=defaults[CONF_AREA]): str,
                vol.Optional(
                    CONF_EXPOSE_ALL_PARAMETERS,
                    default=defaults[CONF_EXPOSE_ALL_PARAMETERS],
                ): bool,
                vol.Optional(
                    CONF_ENABLE_MEASUREMENTS,
                    default=defaults[CONF_ENABLE_MEASUREMENTS],
                ): bool,
                vol.Optional(
                    CONF_FIELD_OVERRIDES, default=defaults[CONF_FIELD_OVERRIDES]
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
