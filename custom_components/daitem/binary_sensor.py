"""Binary sensors: faults on the panel and its devices, and detector inhibition.

Important: the API exposes **no** live open/closed detector state, so no door or window
contact can be created. What is available are the **faults** (power, tamper, transmission
media, battery, radio, masking...) and the inhibition flag, exposed here.

Fault entities are built from the library's `Fault` enum, never from raw API keys, so a
renamed field on the Daitem side is absorbed by the library alone.

Controls (remotes, keypads) get the same treatment as detectors, except that a live
installation reports an empty `anomalies` block for them, so in practice their only entity
is the inhibition one. That is enough to keep the device from being an empty shell.
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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity_registry import RegistryEntryHider
from pydaitem import Device, Fault, Inventory

from .const import DOMAIN, OPTION_FAULT_VISIBILITY_MIGRATED
from .coordinator import DaitemConfigEntry, DaitemCoordinator
from .device import DaitemDeviceEntity, device_key
from .entity import DaitemEntity

_LOGGER = logging.getLogger(__name__)

#: Read-only platform: the coordinator drives refreshes on its own.
PARALLEL_UPDATES = 0

#: Faults the panel itself reports, with the matching Home Assistant device class.
#:
#: Names and icons are not here: both are keyed on `fault.value` in `strings.json` and
#: `icons.json`, which is what gives each fault its own translated label and its own icon
#: instead of the single generic one the device class would produce for all of them.
CENTRAL_FAULTS: dict[Fault, BinarySensorDeviceClass] = {
    Fault.MAIN_POWER: BinarySensorDeviceClass.PROBLEM,
    Fault.BACKUP_POWER: BinarySensorDeviceClass.PROBLEM,
    Fault.TRANSMISSION_MEDIA: BinarySensorDeviceClass.PROBLEM,
    Fault.TAMPER_MECHANICAL: BinarySensorDeviceClass.TAMPER,
    Fault.TAMPER_WIRED: BinarySensorDeviceClass.TAMPER,
}

#: Faults an individual detector may report. Only created for the anomaly keys a given
#: device actually exposes, since detector types vary (a door contact does not report the
#: same anomalies as a smoke head).
DETECTOR_FAULTS: dict[Fault, BinarySensorDeviceClass] = {
    Fault.BATTERY: BinarySensorDeviceClass.BATTERY,
    Fault.RADIO: BinarySensorDeviceClass.PROBLEM,
    Fault.MASKING: BinarySensorDeviceClass.TAMPER,
    Fault.TAMPER_MECHANICAL: BinarySensorDeviceClass.TAMPER,
    Fault.TAMPER_WIRED: BinarySensorDeviceClass.TAMPER,
    Fault.SENSOR: BinarySensorDeviceClass.PROBLEM,
    Fault.LOOP: BinarySensorDeviceClass.PROBLEM,
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
        DaitemCentralFault(coordinator, fault, device_class) for fault, device_class in CENTRAL_FAULTS.items()
    )

    # Detector entities depend on knowing which devices exist, so unlike the central
    # faults there is no fixed list to fall back on if the first inventory read failed.
    # The device list is assumed stable; reloading the integration picks up a recovery.
    inventory = coordinator.inventory
    if inventory is None:
        _LOGGER.warning(
            "The device inventory was unreadable at startup, so no per-detector fault "
            "sensor could be created. Panel fault sensors are unaffected. Reload the "
            "integration once the inventory is readable to get the detector sensors."
        )
        return

    _migrate_fault_visibility(hass, entry, coordinator, inventory)

    async_add_entities(
        DaitemDeviceFault(coordinator, device, fault, device_class=device_class)
        for device in inventory.devices
        for fault, device_class in DETECTOR_FAULTS.items()
        if device.anomalies.has(fault) is not None
    )

    # A control reports no fault of its own, so this is usually its only entity. Without
    # it the device would carry none at all, and Home Assistant prunes those.
    #
    # `inhibited` counts as well as `inhibitable`: the library defaults both to False when
    # the key is missing, and a device reporting itself inhibited without advertising that
    # it can be would otherwise hide the very hole this entity exists to show.
    async_add_entities(
        DaitemDeviceInhibited(coordinator, device)
        for device in inventory.devices
        if device.inhibitable or device.inhibited
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
    for device in inventory.devices:
        for fault in DETECTOR_FAULTS:
            if fault in DEFAULT_VISIBLE_DETECTOR_FAULTS:
                continue
            unique_id = f"{device_key(coordinator.system_id, device)}_{fault.value}"
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
        device_class: BinarySensorDeviceClass,
    ) -> None:
        super().__init__(coordinator)
        self._fault = fault
        self._attr_translation_key = fault.value
        self._attr_device_class = device_class
        self._attr_unique_id = f"{coordinator.system_id}_central_{fault.value}"

    @property
    def is_on(self) -> bool | None:
        """Whether the fault is raised, or None while the inventory is unavailable."""
        inventory = self.coordinator.inventory
        return inventory.central_anomalies.has(self._fault) if inventory else None


class DaitemDeviceFault(DaitemDeviceEntity, BinarySensorEntity):
    """A single fault reported by one detector or control."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: DaitemCoordinator,
        device: Device,
        fault: Fault,
        *,
        device_class: BinarySensorDeviceClass,
    ) -> None:
        super().__init__(coordinator, device)
        self._fault = fault
        self._attr_entity_registry_visible_default = fault in DEFAULT_VISIBLE_DETECTOR_FAULTS
        self._attr_translation_key = fault.value
        self._attr_device_class = device_class
        self._attr_unique_id = f"{self.device_key}_{fault.value}"

    @property
    def is_on(self) -> bool | None:
        """Whether the fault is raised, or None while the inventory is unavailable."""
        device = self.current_device()
        return device.anomalies.has(self._fault) if device else None


class DaitemDeviceInhibited(DaitemDeviceEntity, BinarySensorEntity):
    """Whether a detector or control is deliberately neutralised.

    Visible by default, unlike the faults: an inhibited detector is a hole in the
    protection while the system is armed, and that is something to notice without going
    looking for it.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "inhibited"

    def __init__(self, coordinator: DaitemCoordinator, device: Device) -> None:
        super().__init__(coordinator, device)
        self._attr_unique_id = f"{self.device_key}_inhibited"

    @property
    def is_on(self) -> bool | None:
        device = self.current_device()
        return device.inhibited if device else None
