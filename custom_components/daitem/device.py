"""Shared base for entities that belong to one device of the inventory rather than the panel.

Every family the inventory lists (detectors, controls, sirens, transmitters, transceivers,
the box, fire and PPMS triggers) has the same shape in the API, and the integration treats
them the same way: one Home Assistant device each, hanging off the panel.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from pydaitem import Device, DeviceKind

from .const import DOMAIN
from .coordinator import DaitemCoordinator
from .entity import DaitemEntity

#: What a device is called when the installation left its name blank, by kind. Indices are
#: numbered per family, so the family has to be in the name for two unnamed devices of
#: different families not to read the same.
_FALLBACK_NAMES: dict[DeviceKind, str] = {
    DeviceKind.SENSOR: "Detector",
    DeviceKind.COMMAND: "Control",
    DeviceKind.SIREN: "Siren",
    DeviceKind.TRANSMITTER: "Transmitter",
    DeviceKind.TRANSCEIVER: "Transceiver",
    DeviceKind.BOX: "Box",
    DeviceKind.FIRE_TRIGGER: "Fire trigger",
    DeviceKind.PPMS_TRIGGER: "PPMS trigger",
}


def device_key(system_id: int, device: Device) -> str:
    """Identity of one device, unique across every family.

    `Device.index` is numbered per list, not globally: on a live installation the detectors
    run 1 to 9 and the controls 1 to 4, so the index alone collides. Including `kind`
    separates them, and for a detector it reproduces exactly the identifiers already in the
    registry, so nothing existing is renumbered.
    """
    return f"{system_id}_{device.kind}_{device.index}"


def display_name(device: Device) -> str:
    """What to call a device, falling back to its kind and index when unnamed.

    Shared with the `groups` attribute on the alarm entity, so a detector the installation
    left unnamed reads the same there as on its own device page rather than as a blank.
    """
    if device.name:
        return device.name
    fallback = _FALLBACK_NAMES.get(device.kind, "Device")
    # The box has no index of its own: the library reads 0, which would only add noise.
    return f"{fallback} {device.index}" if device.index else fallback


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device_key)},
            manufacturer="Daitem",
            name=display_name(device),
            model=device.type or None,
            serial_number=device.serial_number or None,
            sw_version=firmware_version(device),
            via_device_id=coordinator.panel_device_id,
        )

    def current_device(self) -> Device | None:
        """The device as of the latest inventory, or None while it is unavailable."""
        inventory = self.coordinator.inventory
        if inventory is None:
            return None
        return next(
            (d for d in inventory.devices if d.index == self._index and d.kind == self._kind),
            None,
        )
