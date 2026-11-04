"""Config flow for the Hargassner Cloud integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CloudApiClient
from .const import (
    CONF_AREA,
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_INSTALLATION,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_BASE_URL,
    DOMAIN,
)
from .exceptions import (
    CloudAuthError,
    CloudClientCredentialsError,
    CloudConnectionError,
    CloudMaintenanceError,
)
from .options_flow import HargassnerCloudOptionsFlow

_LOGGER = logging.getLogger(__name__)


class HargassnerCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Hargassner Cloud config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending_data: dict[str, Any] | None = None
        self._installations: list[dict[str, str]] = []

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HargassnerCloudOptionsFlow:
        return HargassnerCloudOptionsFlow()

    def _client(self, data: Mapping[str, Any]) -> CloudApiClient:
        return CloudApiClient(
            async_get_clientsession(self.hass),
            base_url=data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            installation=data.get(CONF_INSTALLATION, ""),
            client_id=data.get(CONF_CLIENT_ID),
            client_secret=data.get(CONF_CLIENT_SECRET),
        )

    @staticmethod
    def _handle_error(err: Exception, errors: dict[str, str]) -> None:
        if isinstance(err, CloudAuthError):
            errors["base"] = "auth"
        elif isinstance(err, CloudClientCredentialsError):
            errors["base"] = "web_client_credentials"
        elif isinstance(err, CloudMaintenanceError):
            errors["base"] = "maintenance"
        elif isinstance(err, (CloudConnectionError, ClientError, TimeoutError)):
            errors["base"] = "cannot_connect"
        else:
            _LOGGER.exception("Unexpected Hargassner Cloud setup failure")
            errors["base"] = "unknown"

    async def _async_finish_setup(
        self, data: dict[str, Any], installation_id: str
    ) -> ConfigFlowResult:
        data = {**data, CONF_INSTALLATION: installation_id}
        await self.async_set_unique_id(installation_id)
        self._abort_if_unique_id_configured()
        name = next(
            (
                item["name"]
                for item in self._installations
                if item["id"] == installation_id
            ),
            "Hargassner Cloud",
        )
        return self.async_create_entry(title=name, data=data)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                client = self._client(user_input)
                await client.authenticate()
                self._installations = await client.fetch_installations()
            except Exception as err:  # noqa: BLE001 - classified below
                self._handle_error(err, errors)
            else:
                if not self._installations:
                    errors["base"] = "no_installations"
                elif len(self._installations) == 1:
                    return await self._async_finish_setup(
                        user_input, self._installations[0]["id"]
                    )
                else:
                    self._pending_data = user_input
                    return await self.async_step_installation()

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
                vol.Optional(CONF_AREA, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_installation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._pending_data is None or not self._installations:
            return self.async_abort(reason="cannot_connect")
        if user_input is not None:
            return await self._async_finish_setup(
                self._pending_data, str(user_input[CONF_INSTALLATION])
            )
        choices = {item["id"]: item["name"] for item in self._installations}
        return self.async_show_form(
            step_id="installation",
            data_schema=vol.Schema(
                {vol.Required(CONF_INSTALLATION): vol.In(choices)}
            ),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            updated = {**entry.data, **user_input}
            try:
                await self._client(updated).authenticate()
            except Exception as err:  # noqa: BLE001 - classified below
                self._handle_error(err, errors)
            else:
                await self.async_set_unique_id(str(updated[CONF_INSTALLATION]))
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")
                ): str,
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors
        )
