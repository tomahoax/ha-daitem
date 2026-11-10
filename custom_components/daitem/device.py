"""Shared base for entities that belong to one device of the inventory rather than the panel.

Every family the inventory lists (detectors, controls, sirens, transmitters, transceivers,
the box, fire and PPMS triggers) has the same shape in the API, and the integration treats
them the same way: one Home Assistant device each, hanging off the panel.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from pydaitem import Device

from .const import DOMAIN
from .coordinator import DaitemConfigEntry, DaitemCoordinator, DaitemData
from .entity import DaitemEntity
from .keys import device_key


def inventory_devices(system_id: int, data: DaitemData) -> dict[str, Device]:
    """Every device of the latest inventory, keyed by its device identifier.

    Empty while the inventory has never been read, which simply defers the entities to the
    first cycle that reads it.
    """
    inventory = data.inventory
    return {device_key(system_id, d): d for d in inventory.devices} if inventory else {}


def device_info(coordinator: DaitemCoordinator, device: Device) -> DeviceInfo:
    """How one inventory device is described, the same way wherever it is registered.

    A name given in the app is kept as it is. An unnamed device is named by Home Assistant
    in its own language from the family's translation ("Détecteur 3", "Siren 1"), since the
    integration should not hard-code an English name.
    """
    info = DeviceInfo(
        identifiers={(DOMAIN, device_key(coordinator.system_id, device))},
        manufacturer="Daitem",
        model=device.type or None,
        serial_number=device.serial_number or None,
        sw_version=firmware_version(device),
        via_device_id=coordinator.panel_device_id,
    )
    if device.name:
        info["name"] = device.name
    else:
        info["translation_key"] = str(device.kind)
        info["translation_placeholders"] = {"index": str(device.index)}
    return info


@callback
def async_register_inventory_devices(hass: HomeAssistant, entry: DaitemConfigEntry) -> None:
    """Register every device of the inventory, before the platforms describe them.

    The registry resolves a translated name at registration. Doing it here means the alarm
    entity's `groups` attribute can read that name, whichever platform comes up first.
    """
    coordinator = entry.runtime_data
    inventory = coordinator.inventory
    if inventory is None:
        return
    registry = dr.async_get(hass)
    for device in inventory.devices:
        registry.async_get_or_create(config_entry_id=entry.entry_id, **device_info(coordinator, device))


def registered_name(hass: HomeAssistant, entry: DaitemConfigEntry, device: Device) -> str:
    """What the device page calls a device: the user's rename, else its registered name.

    For state attributes, which Home Assistant does not translate.
    """
    key = device_key(entry.runtime_data.system_id, device)
    registered = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, key), entry.entry_id)
    if registered is not None and (name := registered.name_by_user or registered.name):
        return name
    return device.name or key


def firmware_version(device: Device) -> str | None:
    """The version of the device's own software, the main one first, None when unreported.

    Most devices report none, so this is mostly for the box and the transmission modules.
    """
    versions = sorted((f for f in device.firmwares if f.version), key=lambda f: f.kind != "SOFT")
    return versions[0].version if versions else None


class DaitemDeviceEntity(DaitemEntity):
    """Attaches the entity to its own device: a detector, a control, a siren..."""

    def __init__(self, coordinator: DaitemCoordinator, device: Device) -> None:
        super().__init__(coordinator)
        self._index = device.index
        self._kind = device.kind
        self.device_key = device_key(coordinator.system_id, device)
        self._attr_device_info = device_info(coordinator, device)

    def current_device(self) -> Device | None:
        """The device as of the latest inventory, or None while it is unavailable."""
        inventory = self.coordinator.inventory
        if inventory is None:
            return None
        return next(
            (d for d in inventory.devices if d.index == self._index and d.kind == self._kind),
            None,
        )
