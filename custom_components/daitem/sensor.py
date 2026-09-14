"""Diagnostic readouts taken from the inventory: firmware versions and group membership.

None of this changes, or changes so rarely that polling it is free: it rides along with
the inventory the coordinator already fetches every cycle for the fault sensors.

Everything here is hidden by default. A firmware version and a group number are facts you
look up once, not things worth a row on a dashboard, and the panel page already carries
enough entities.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaitem import Device, Inventory

from .coordinator import DaitemConfigEntry, DaitemCoordinator
from .device import DaitemDeviceEntity
from .entity import DaitemEntity

_LOGGER = logging.getLogger(__name__)

#: Read-only platform: the coordinator drives refreshes on its own.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class FirmwareDescription:
    """One firmware version the panel reports about itself."""

    key: str
    value: Callable[[Inventory], str | None]


#: The panel carries two images, its transmission module a third. There is no firmware
#: version per detector: the API exposes none, so none is invented.
FIRMWARES: tuple[FirmwareDescription, ...] = (
    FirmwareDescription(key="firmware_software", value=lambda inv: inv.software_version),
    FirmwareDescription(key="firmware_radio", value=lambda inv: inv.radio_version),
    FirmwareDescription(key="firmware_transmitter", value=lambda inv: inv.transmitter_version),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaitemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    inventory = coordinator.inventory
    if inventory is None:
        # Everything on this platform is read out of the inventory, so an unreadable one at
        # startup leaves the platform empty until a reload. Said out loud, because all of
        # these entities are hidden by default: their absence is otherwise invisible.
        _LOGGER.warning(
            "The device inventory was unreadable at startup, so no firmware or group "
            "sensor could be created. Reload the integration once the inventory is "
            "readable to get them."
        )
        return

    # Only for the versions this installation actually reports, so a panel that returns no
    # firmware block does not end up with three entities stuck on unknown forever.
    async_add_entities(
        DaitemFirmware(coordinator, description)
        for description in FIRMWARES
        if description.value(inventory) is not None
    )

    # Controls report no group, only detectors do (confirmed on a live installation).
    async_add_entities(
        DaitemDeviceGroup(coordinator, device) for device in inventory.devices if device.group is not None
    )


class DaitemFirmware(DaitemEntity, SensorEntity):
    """One firmware version of the panel."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_visible_default = False

    def __init__(self, coordinator: DaitemCoordinator, description: FirmwareDescription) -> None:
        super().__init__(coordinator)
        self._description = description
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{coordinator.system_id}_{description.key}"

    @property
    def native_value(self) -> str | None:
        inventory = self.coordinator.inventory
        return self._description.value(inventory) if inventory else None


class DaitemDeviceGroup(DaitemDeviceEntity, SensorEntity):
    """Which group a detector belongs to.

    The API gives a number and no name: group names appear nowhere in the inventory, and
    the state payload's `groupList` has never been observed carrying one.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_visible_default = False
    _attr_translation_key = "group"

    def __init__(self, coordinator: DaitemCoordinator, device: Device) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{self.device_key}_group"

    @property
    def native_value(self) -> int | None:
        device = self.current_device()
        return device.group if device else None
