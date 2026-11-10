"""Shared base class for Daitem entities."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DaitemConfigEntry, DaitemCoordinator, DaitemData


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


def async_track_new[T](
    entry: DaitemConfigEntry,
    source: str,
    items: Callable[[DaitemData], Mapping[str, T]],
    create: Callable[[T], Iterable[Entity]],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Make entities for what the Daitem app holds now, and for what it gains later.

    Home Assistant's `dynamic-devices` pattern: on every update of the coordinator, the keys
    `items` returns are compared with those already seen, and only the new ones get
    entities. A detector learnt by the installer, or an automation, a scenario or a camera
    added in the app, then appears without reloading the integration.

    `source` names this platform's list, so two platforms reading the same items keep their
    own memory. Keys are device identifiers wherever there is a device, which is what lets
    a device deleted by hand be forgotten, and recreated if it ever comes back.
    """
    coordinator = entry.runtime_data
    known = coordinator.known.setdefault(source, set())

    @callback
    def check() -> None:
        if coordinator.data is None:
            return
        current = items(coordinator.data)
        new = [key for key in current if key not in known]
        if not new:
            return
        known.update(new)
        entities = [entity for key in new for entity in create(current[key])]
        if entities:
            async_add_entities(entities)

    check()
    entry.async_on_unload(coordinator.async_add_listener(check))
