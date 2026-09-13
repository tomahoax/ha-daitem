"""Refresh token persistence backed by the config entry.

Without this, Home Assistant replays the full Keycloak login form on every restart. Storing
the refresh token in the config entry lets it resume the session instead.

The config entry is the right place: Home Assistant already persists it alongside the other
credentials, and it needs no disk I/O of our own inside the event loop.

Note that config entries are stored as plain JSON in `.storage/core.config_entries`,
protected by file permissions only. The refresh token therefore sits in the clear next to
the password and the alarm code, so a configuration backup carries all three.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

CONF_REFRESH_TOKEN = "refresh_token"


class ConfigEntryTokenStore:
    """Implements the pydaitem TokenStore protocol on top of a config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry

    async def load(self) -> str | None:
        token = self._entry.data.get(CONF_REFRESH_TOKEN)
        return token if isinstance(token, str) and token else None

    async def save(self, refresh_token: str | None) -> None:
        if self._entry.data.get(CONF_REFRESH_TOKEN) == refresh_token:
            # Keycloak often returns the same token, so avoid rewriting the entry and
            # triggering a reload listener for nothing.
            return

        data = dict(self._entry.data)
        if refresh_token is None:
            data.pop(CONF_REFRESH_TOKEN, None)
        else:
            data[CONF_REFRESH_TOKEN] = refresh_token

        try:
            self._hass.config_entries.async_update_entry(self._entry, data=data)
        except HomeAssistantError as err:
            # The entry can disappear while a request is in flight, for instance if the
            # user removes the integration mid-poll. Rotating a token we can no longer
            # store is harmless, so this must not surface as a command failure.
            _LOGGER.debug("Config entry gone, refresh token not persisted: %s", err)
