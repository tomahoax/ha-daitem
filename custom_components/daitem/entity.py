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
        inventory = coordinator.data.inventory if coordinator.data else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.system_id))},
            manufacturer="Daitem",
            translation_key="panel",
            translation_placeholders={"installation_name": coordinator.config_entry.title},
            model=inventory.central_type if inventory else None,
            serial_number=inventory.central_serial if inventory else None,
        )

    @property
    def available(self) -> bool:
        """A session held by another device is not an outage.

        We stay available as long as we hold a state, even a slightly stale one: making
        the alarm unavailable because the user opened the mobile app would be poor UX.
        """
        return super().available and self.coordinator.data is not None
