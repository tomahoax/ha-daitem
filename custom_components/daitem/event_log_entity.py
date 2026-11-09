"""Shared base for the entities fed by the event log coordinator."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .event_log import DaitemEventLogCoordinator


class DaitemEventLogEntity(CoordinatorEntity[DaitemEventLogCoordinator]):
    """Attached to the panel device, like every panel-level entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DaitemEventLogCoordinator, system_id: int) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, str(system_id))})
