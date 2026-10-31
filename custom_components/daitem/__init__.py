"""Home Assistant integration for Daitem alarms (Atral Topaze platform).

Unofficial integration built on the pydaitem library, which consumes the private API of
the Daitem Secure app. Not affiliated with or endorsed by Daitem or Atral.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
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
    Platform.SENSOR,
]

SERVICE_ARM_GROUPS = "arm_groups"
ATTR_GROUPS = "groups"
ATTR_ACTIVE = "active"
ATTR_ENTITY_ID = "entity_id"

SERVICE_ARM_GROUPS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_GROUPS): vol.All(cv.ensure_list, [vol.Coerce(int)]),
        vol.Optional(ATTR_ACTIVE, default=True): cv.boolean,
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    }
)


def _async_setup_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_ARM_GROUPS):
        return

    async def async_handle_arm_groups(call: ServiceCall) -> None:
        raw_groups: list[int] = call.data[ATTR_GROUPS]
        active: bool = call.data.get(ATTR_ACTIVE, True)
        target_entity_ids = call.data.get(ATTR_ENTITY_ID)

        group_map = {int(gid): active for gid in raw_groups}

        entries: list[DaitemConfigEntry] = hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            coordinator: DaitemCoordinator | None = getattr(entry, "runtime_data", None)
            if coordinator is None:
                continue

            if target_entity_ids:
                system_id_str = str(coordinator.system_id)
                matched = any(system_id_str in eid or eid.endswith("_alarm") for eid in target_entity_ids)
                if not matched and len(entries) > 1:
                    continue

            status = await coordinator.system.commands.arm_groups(group_map)
            await coordinator.async_apply_command_result(status)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ARM_GROUPS,
        async_handle_arm_groups,
        schema=SERVICE_ARM_GROUPS_SCHEMA,
    )


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
    _async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DaitemConfigEntry) -> bool:
    """Unload the installation."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and not any(
        e.entry_id != entry.entry_id and getattr(e, "runtime_data", None)
        for e in hass.config_entries.async_entries(DOMAIN)
    ):
        hass.services.async_remove(DOMAIN, SERVICE_ARM_GROUPS)
    return unloaded
