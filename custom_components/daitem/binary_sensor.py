"""Fault binary sensors for the panel and its individual detectors.

Important: the API exposes **no** live open/closed detector state, so no door or window
contact can be created. What is available are the **faults** (power, tamper, transmission
media, battery, radio, masking...), exposed here.

Entities are built from the library's `Fault` enum, never from raw API keys, so a renamed
field on the Daitem side is absorbed by the library alone.
"""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity_registry import RegistryEntryHider
from pydaitem import Device, Fault, Inventory

from .const import DOMAIN, OPTION_FAULT_VISIBILITY_MIGRATED
from .coordinator import DaitemConfigEntry, DaitemCoordinator
from .entity import DaitemEntity

_LOGGER = logging.getLogger(__name__)

#: Read-only platform: the coordinator drives refreshes on its own.
PARALLEL_UPDATES = 0

#: Faults the panel itself reports, with the matching Home Assistant device class.
CENTRAL_FAULTS: dict[Fault, tuple[str, BinarySensorDeviceClass]] = {
    Fault.MAIN_POWER: ("Main power supply", BinarySensorDeviceClass.PROBLEM),
    Fault.BACKUP_POWER: ("Backup power supply", BinarySensorDeviceClass.PROBLEM),
    Fault.TRANSMISSION_MEDIA: ("Transmission media", BinarySensorDeviceClass.PROBLEM),
    Fault.TAMPER_MECHANICAL: ("Mechanical tamper", BinarySensorDeviceClass.TAMPER),
    Fault.TAMPER_WIRED: ("Wired tamper", BinarySensorDeviceClass.TAMPER),
}

#: Faults an individual detector may report. Only created for the anomaly keys a given
#: device actually exposes, since detector types vary (a door contact does not report the
#: same anomalies as a smoke head).
DETECTOR_FAULTS: dict[Fault, tuple[str, BinarySensorDeviceClass]] = {
    Fault.BATTERY: ("Battery", BinarySensorDeviceClass.BATTERY),
    Fault.RADIO: ("Radio", BinarySensorDeviceClass.PROBLEM),
    Fault.MASKING: ("Masking", BinarySensorDeviceClass.TAMPER),
    Fault.TAMPER_MECHANICAL: ("Mechanical tamper", BinarySensorDeviceClass.TAMPER),
    Fault.TAMPER_WIRED: ("Wired tamper", BinarySensorDeviceClass.TAMPER),
    Fault.SENSOR: ("Sensor fault", BinarySensorDeviceClass.PROBLEM),
    Fault.LOOP: ("Loop fault", BinarySensorDeviceClass.PROBLEM),
}

#: Only these are visible out of the box. A detector typically reports six faults, so a
#: nine-detector installation would otherwise dump 50+ entities in the user's list. The
#: others are still created (state, history, automations), just hidden. This applies at
#: first registration only: an already-registered entity keeps its current visibility.
DEFAULT_VISIBLE_DETECTOR_FAULTS = frozenset({Fault.BATTERY, Fault.RADIO})


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaitemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    # Central fault entities are created unconditionally rather than from the first
    # payload: a transient inventory failure at startup must not permanently deprive the
    # user of fault reporting. A fault the panel does not report simply stays unknown.
    async_add_entities(
        DaitemCentralFault(coordinator, fault, label, device_class)
        for fault, (label, device_class) in CENTRAL_FAULTS.items()
    )

    # Detector entities depend on knowing which devices exist, so unlike the central
    # faults there is no fixed list to fall back on if the first inventory read failed.
    # The device list is assumed stable; reloading the integration picks up a recovery.
    inventory = coordinator.data.inventory if coordinator.data else None
    if inventory is None:
        _LOGGER.warning(
            "The device inventory was unreadable at startup, so no per-detector fault "
            "sensor could be created. Panel fault sensors are unaffected. Reload the "
            "integration once the inventory is readable to get the detector sensors."
        )
        return

    _migrate_fault_visibility(hass, entry, coordinator, inventory)

    # __init__.py registers the panel device before forwarding to this platform, so this
    # lookup cannot race it.
    panel_device_id = dr.async_get_device_id_by_identifier(
        hass, (DOMAIN, str(coordinator.system_id)), config_entry_id=entry.entry_id
    )
    async_add_entities(
        DaitemDetectorFault(
            coordinator, device, fault, label=label, device_class=device_class, panel_device_id=panel_device_id
        )
        for device in inventory.sensors
        for fault, (label, device_class) in DETECTOR_FAULTS.items()
        if device.anomalies.has(fault) is not None
    )


def _migrate_fault_visibility(
    hass: HomeAssistant, entry: DaitemConfigEntry, coordinator: DaitemCoordinator, inventory: Inventory
) -> None:
    """One-off fix for entities that come back visible after a reinstall.

    Removing a config entry does not erase its entities from the registry: Home Assistant
    keeps them in a `deleted_entities` record and, if the same unique id is registered
    again, restores their previous `hidden_by` instead of applying the current
    `entity_registry_visible_default` (`entity_registry.py`'s `async_get_or_create` only
    sets `hidden_by` when actually creating a new entry). An entity created before this
    default existed, or removed and re-added since, can therefore reappear visible.

    Runs before `async_add_entities` on purpose: that callback only *schedules* the
    registry write as a background task rather than performing it inline, so anything
    placed after it here could run before the row actually exists. Operating directly on
    the registry sidesteps that race, and is a no-op for an entity that is not registered
    yet - `async_add_entities` will create it correctly moments later regardless.

    Applied once per config entry, tracked in `entry.options`, so a visibility choice made
    afterwards by the user is never overwritten again.
    """
    if entry.options.get(OPTION_FAULT_VISIBILITY_MIGRATED):
        return

    registry = er.async_get(hass)
    for device in inventory.sensors:
        for fault in DETECTOR_FAULTS:
            if fault in DEFAULT_VISIBLE_DETECTOR_FAULTS:
                continue
            unique_id = f"{coordinator.system_id}_sensor_{device.index}_{fault.value}"
            entity_id = registry.async_get_entity_id(BINARY_SENSOR_DOMAIN, DOMAIN, unique_id)
            if entity_id is None:
                continue
            registered = registry.async_get(entity_id)
            if registered is not None and registered.hidden_by is None:
                registry.async_update_entity(entity_id, hidden_by=RegistryEntryHider.INTEGRATION)

    hass.config_entries.async_update_entry(entry, options={**entry.options, OPTION_FAULT_VISIBILITY_MIGRATED: True})


class DaitemCentralFault(DaitemEntity, BinarySensorEntity):
    """A single panel fault."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: DaitemCoordinator,
        fault: Fault,
        label: str,
        device_class: BinarySensorDeviceClass,
    ) -> None:
        super().__init__(coordinator)
        self._fault = fault
        self._attr_name = label
        self._attr_device_class = device_class
        self._attr_unique_id = f"{coordinator.system_id}_central_{fault.value}"

    @property
    def is_on(self) -> bool | None:
        """Whether the fault is raised, or None while the inventory is unavailable."""
        data = self.coordinator.data
        if data is None or data.inventory is None:
            return None
        return data.inventory.central_anomalies.has(self._fault)


class DaitemDetectorFault(DaitemEntity, BinarySensorEntity):
    """A single fault reported by one detector, as its own Home Assistant device."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: DaitemCoordinator,
        device: Device,
        fault: Fault,
        *,
        label: str,
        device_class: BinarySensorDeviceClass,
        panel_device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._index = device.index
        self._fault = fault
        self._attr_entity_registry_visible_default = fault in DEFAULT_VISIBLE_DETECTOR_FAULTS
        self._attr_name = label
        self._attr_device_class = device_class
        self._attr_unique_id = f"{coordinator.system_id}_sensor_{device.index}_{fault.value}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.system_id}_sensor_{device.index}")},
            manufacturer="Daitem",
            name=device.name or f"Detector {device.index}",
            model=device.type or None,
            serial_number=device.serial_number or None,
            via_device_id=panel_device_id,
        )

    def _current_device(self) -> Device | None:
        inventory = self.coordinator.data.inventory if self.coordinator.data else None
        if inventory is None:
            return None
        return next((d for d in inventory.sensors if d.index == self._index), None)

    @property
    def is_on(self) -> bool | None:
        """Whether the fault is raised, or None while the inventory is unavailable."""
        device = self._current_device()
        return device.anomalies.has(self._fault) if device else None
