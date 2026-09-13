"""Config flow for the Daitem integration.

Two steps: account credentials, then installation choice if the account exposes several.
The alarm code requested is the one tied to **the account used**, which is not necessarily
the owner's master code.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pydaitem import DaitemAuthError, DaitemClient, DaitemError, System

from .const import CONF_MASTER_CODE, CONF_SYSTEM_ID, DOMAIN
from .tokens import CONF_REFRESH_TOKEN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_MASTER_CODE): str,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_MASTER_CODE): str,
    }
)


# Ignored below: mypy does not follow Home Assistant sources (follow_imports = skip) so
# it cannot see the ConfigFlow "domain" parameter.
class DaitemConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handles adding a Daitem installation."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._systems: list[System] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            client = DaitemClient(
                user_input[CONF_EMAIL],
                user_input[CONF_PASSWORD],
                session=async_get_clientsession(self.hass),
            )
            try:
                await client.login()
                self._systems = await client.account.list_systems()
            except DaitemAuthError as err:
                _LOGGER.debug("Authentication rejected during setup: %s", err)
                errors["base"] = "invalid_auth"
            except DaitemError as err:
                _LOGGER.debug("Could not reach the Daitem service during setup: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"
            else:
                if not self._systems:
                    errors["base"] = "no_system"
                else:
                    self._data = dict(user_input)
                    if len(self._systems) == 1:
                        return await self._create_entry(self._systems[0])
                    return await self.async_step_system()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_system(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick the installation when the account exposes several."""
        if user_input is not None:
            chosen = next((s for s in self._systems if s.id == int(user_input[CONF_SYSTEM_ID])), None)
            if chosen is None:
                return self.async_abort(reason="no_system")
            return await self._create_entry(chosen)

        return self.async_show_form(
            step_id="system",
            data_schema=vol.Schema(
                {vol.Required(CONF_SYSTEM_ID): vol.In({str(s.id): f"{s.name} ({s.id})" for s in self._systems})}
            ),
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Triggered when authentication fails while running."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the password and code again without recreating the entry."""
        errors: dict[str, str] = {}
        entry: ConfigEntry = self._get_reauth_entry()

        if user_input is not None:
            client = DaitemClient(
                entry.data[CONF_EMAIL],
                user_input[CONF_PASSWORD],
                session=async_get_clientsession(self.hass),
            )
            try:
                await client.login()
            except DaitemAuthError as err:
                _LOGGER.debug("Authentication rejected during re-authentication: %s", err)
                errors["base"] = "invalid_auth"
            except DaitemError as err:
                _LOGGER.debug("Could not reach the Daitem service during re-authentication: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during re-authentication")
                errors["base"] = "unknown"
            else:
                # Pass a full data mapping rather than data_updates, which merges: the
                # stored refresh token must be dropped. People re-authenticate precisely
                # because they changed their password to cut off an old session, and
                # Keycloak does not necessarily revoke the refresh token, so reusing it
                # would resume the very session they meant to end.
                data = {k: v for k, v in entry.data.items() if k != CONF_REFRESH_TOKEN}
                return self.async_update_reload_and_abort(entry, data={**data, **user_input})

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
        )

    async def _create_entry(self, system: System) -> ConfigFlowResult:
        await self.async_set_unique_id(str(system.id))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=system.name or f"Daitem {system.id}",
            data={**self._data, CONF_SYSTEM_ID: system.id},
        )
