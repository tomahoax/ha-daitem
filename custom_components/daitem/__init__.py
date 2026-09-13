"""Home Assistant integration for Daitem alarms (Atral Topaze platform).

Unofficial integration built on the pydaitem library, which consumes the private API of
the Daitem Secure app. Not affiliated with or endorsed by Daitem or Atral.
"""

from __future__ import annotations

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pydaitem import DaitemAuthError, DaitemClient, DaitemError, DaitemSystem

from .const import CONF_MASTER_CODE, CONF_SYSTEM_ID, DOMAIN
from .coordinator import DaitemConfigEntry, DaitemCoordinator
from .tokens import ConfigEntryTokenStore

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: DaitemConfigEntry) -> bool:
    """Set up a Daitem installation."""
    # Reuse Home Assistant's shared aiohttp session rather than opening our own pool, and
    # persist the refresh token so a restart resumes the session instead of replaying the
    # Keycloak login form.
    client = DaitemClient(
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        session=async_get_clientsession(hass),
        token_store=ConfigEntryTokenStore(hass, entry),
    )

    # The façade owns the session protocol and the alarm code; the integration never
    # handles either.
    system = DaitemSystem(client, entry.data[CONF_SYSTEM_ID], entry.data[CONF_MASTER_CODE])
    coordinator = DaitemCoordinator(hass, entry, system)

    try:
        await coordinator.async_config_entry_first_refresh()
        await coordinator.async_load_capabilities()
    except DaitemAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except DaitemError as err:
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = coordinator

    # Registered explicitly, and before the platforms, so the detector entities set up by
    # binary_sensor can look up its device id for `via_device_id` without racing whichever
    # platform would otherwise register it first.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, str(coordinator.system_id))},
        manufacturer="Daitem",
        name=entry.title,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DaitemConfigEntry) -> bool:
    """Unload the installation."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
