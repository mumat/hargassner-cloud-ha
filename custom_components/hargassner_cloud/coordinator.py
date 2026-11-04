"""Data update coordinator for the Hargassner Cloud integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CloudApiClient
from .const import (
    DOMAIN,
    ISSUE_WEB_CLIENT_CREDENTIALS,
    ISSUE_URL,
    NAME,
)
from .exceptions import (
    CloudApiError,
    CloudAuthError,
    CloudClientCredentialsError,
    CloudConnectionError,
    CloudError,
    CloudMaintenanceError,
)
from .models import InstallationState, parse_state

_LOGGER = logging.getLogger(__name__)


class CloudCoordinator(DataUpdateCoordinator[InstallationState]):
    """Poll the Hargassner Cloud and share the parsed result with all entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: CloudApiClient,
        *,
        update_interval: int,
        enable_measurements: bool,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=NAME,
            config_entry=entry,
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client
        self.enable_measurements = enable_measurements

    # -- repair issues -----------------------------------------------------

    @property
    def _issue_id(self) -> str:
        return f"{ISSUE_WEB_CLIENT_CREDENTIALS}_{self.config_entry.entry_id}"

    def _async_create_credential_issue(self) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            is_fixable=False,
            is_persistent=True,
            learn_more_url=ISSUE_URL,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_WEB_CLIENT_CREDENTIALS,
        )

    def _async_delete_credential_issue(self) -> None:
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)

    # -- polling -----------------------------------------------------------

    async def _async_update_data(self) -> InstallationState:
        try:
            payload = await self.client.fetch_widgets()
        except CloudAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CloudClientCredentialsError as err:
            self._async_create_credential_issue()
            raise UpdateFailed(str(err)) from err
        except CloudMaintenanceError as err:
            raise UpdateFailed(str(err)) from err
        except (CloudConnectionError, CloudApiError) as err:
            raise UpdateFailed(str(err)) from err

        measurements = []
        if self.enable_measurements:
            try:
                measurements = await self.client.fetch_measurements()
            except CloudError as err:
                _LOGGER.debug("Optional measurement fetch failed: %s", err)

        self._async_delete_credential_issue()
        meta = payload.get("meta")
        return InstallationState(
            widgets=parse_state(payload),
            meta=meta if isinstance(meta, dict) else {},
            measurements=measurements,
            raw=payload,
        )
