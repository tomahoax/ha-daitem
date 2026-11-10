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

from .connectivity import DaitemConnectivityCoordinator
from .const import CALL_TIMEOUT, CONF_MASTER_CODE, CONF_SYSTEM_ID, DOMAIN
from .coordinator import DaitemConfigEntry, DaitemCoordinator
from .event_log import DaitemEventLogCoordinator
from .tokens import ConfigEntryTokenStore

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
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
        call_timeout=CALL_TIMEOUT,
    )

    # The façade owns the session protocol and the alarm code; the integration never
    # handles either.
    system = DaitemSystem(client, entry.data[CONF_SYSTEM_ID], entry.data[CONF_MASTER_CODE])
    coordinator = DaitemCoordinator(hass, entry, system)

    # Arming mode discovery is not called here: the first refresh runs it itself, and only
    # once the state read has proved the panel free. Calling it again would open a second
    # session against a panel that tolerates one, at the very moment contention is most
    # likely, which is what used to cost the installation its presence arming.
    try:
        await coordinator.async_config_entry_first_refresh()
    except DaitemAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except DaitemError as err:
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = coordinator

    # Read once now, so its entities exist only for accounts allowed to read it. A failure
    # other than a refusal still creates them: they wait, unavailable, for a later read.
    event_log = DaitemEventLogCoordinator(hass, entry, system)
    await event_log.async_refresh()
    coordinator.event_log = None if event_log.forbidden else event_log

    # Same rule for the transmitter's connectivity: no panel session, its own pace, so it
    # stays readable while the panel is not.
    connectivity = DaitemConnectivityCoordinator(hass, entry, system)
    await connectivity.async_refresh()
    coordinator.connectivity = None if connectivity.forbidden else connectivity

    # Registered explicitly, and before the platforms, so the per-device entities can hang
    # off it through `via_device_id` without racing whichever platform would otherwise
    # register it first. Its id is kept on the coordinator rather than looked up again by
    # each platform, so every platform declares the same parent.
    panel_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, str(coordinator.system_id))},
        manufacturer="Daitem",
        translation_key="panel",
        translation_placeholders={"installation_name": entry.title},
    )
    coordinator.panel_device_id = panel_device.id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DaitemConfigEntry) -> bool:
    """Unload the installation."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = entry.runtime_data
        await coordinator.async_shutdown()
        for secondary in (coordinator.event_log, coordinator.connectivity):
            if secondary is not None:
                await secondary.async_shutdown()
    return unloaded
