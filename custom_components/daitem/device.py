"""Shared base for entities that belong to one detector or control rather than the panel.

Detectors and controls are the same shape in the API, and the integration treats them the
same way: one Home Assistant device each, hanging off the panel.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from pydaitem import Device

from .const import DOMAIN
from .coordinator import DaitemCoordinator
from .entity import DaitemEntity

#: What a device is called when the installation left its name blank, by kind.
_FALLBACK_NAMES = {"sensor": "Detector", "command": "Control"}


def device_key(system_id: int, device: Device) -> str:
    """Identity of one detector or control, unique across both.

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
    fallback = _FALLBACK_NAMES.get(device.kind, "Device")
    return device.name or f"{fallback} {device.index}"


class DaitemDeviceEntity(DaitemEntity):
    """Attaches the entity to its own detector or control device."""

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
