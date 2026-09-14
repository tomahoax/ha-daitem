"""Shared base class for Daitem entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DaitemCoordinator


class DaitemEntity(CoordinatorEntity[DaitemCoordinator]):
    """Attaches the entity to the panel device and handles availability."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DaitemCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.system_id))},
            manufacturer="Daitem",
            translation_key="panel",
            translation_placeholders={"installation_name": coordinator.config_entry.title},
        )
        # Only added when the inventory is readable: Home Assistant treats a key present
        # with a None value as "clear it", so passing them blindly would wipe the model,
        # serial and firmware the registry already holds whenever a restart happens to
        # land on a cycle where the inventory could not be read.
        if (inventory := coordinator.inventory) is not None:
            self._attr_device_info["model"] = inventory.central_type
            self._attr_device_info["serial_number"] = inventory.central_serial
            # Only the main software: the panel also reports a radio version and its
            # transmission module a third, and two registry fields cannot hold three.
            # The other two are sensors.
            self._attr_device_info["sw_version"] = inventory.software_version

    @property
    def available(self) -> bool:
        """A session held by another device is not an outage.

        We stay available as long as we hold a state, even a slightly stale one: making
        the alarm unavailable because the user opened the mobile app would be poor UX.
        """
        return super().available and self.coordinator.data is not None
