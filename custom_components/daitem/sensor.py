"""Readouts: firmware versions and groups, camera status, the latest clip and log entry.

Firmware versions and group membership come from the inventory:

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
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from pydaitem import Camera, Device, Inventory

from .const import DOMAIN
from .coordinator import DaitemConfigEntry, DaitemCoordinator, DaitemData
from .device import DaitemDeviceEntity, inventory_devices
from .entity import DaitemEntity, async_track_new
from .event_log import DaitemEventLogCoordinator
from .event_log_entity import DaitemEventLogEntity

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
    sid = coordinator.system_id
    if coordinator.event_log is not None:
        async_add_entities([DaitemLastEvent(coordinator.event_log, sid)])

    # Every list below follows the reads: what the app gains later, or what an unreadable
    # first read hid, gets its entity on the next cycle that reads it.

    # Only for the versions this installation actually reports, so a panel that returns no
    # firmware block does not end up with three entities stuck on unknown forever.
    def firmwares(data: DaitemData) -> dict[str, FirmwareDescription]:
        inventory = data.inventory
        return {d.key: d for d in FIRMWARES if inventory and d.value(inventory) is not None}

    async_track_new(
        entry, "sensor.firmwares", firmwares, lambda d: [DaitemFirmware(coordinator, d)], async_add_entities
    )

    # Controls report no group, only detectors do (confirmed on a live installation).
    def grouped(data: DaitemData) -> dict[str, Device]:
        return {key: d for key, d in inventory_devices(sid, data).items() if d.group is not None}

    async_track_new(entry, "sensor.groups", grouped, lambda d: [DaitemDeviceGroup(coordinator, d)], async_add_entities)

    def cameras(data: DaitemData) -> dict[str, Camera]:
        return {f"{sid}_camera_{c.id}": c for c in data.cameras}

    async_track_new(
        entry, "sensor.cameras", cameras, lambda c: [DaitemCameraStatus(coordinator, c)], async_add_entities
    )

    # One sensor, once the installation shows any video hardware or clip.
    def video(data: DaitemData) -> dict[str, None]:
        devices = data.inventory.devices if data.inventory else []
        found = data.cameras or data.clips or any(d.is_video for d in devices)
        return {"last_clip": None} if found else {}

    async_track_new(entry, "sensor.last_clip", video, lambda _: [DaitemLastClip(coordinator)], async_add_entities)


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

    The API gives a number and no name: group names appear neither in the inventory nor in
    the state payload's `groupList`.
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


class DaitemCameraStatus(DaitemEntity, SensorEntity):
    """What the API says about one camera. Live video is not reachable through it."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "camera_status"

    def __init__(self, coordinator: DaitemCoordinator, camera: Camera) -> None:
        super().__init__(coordinator)
        self._camera_id = camera.id
        key = f"{coordinator.system_id}_camera_{camera.id}"
        self._attr_unique_id = f"{key}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, key)},
            manufacturer="Daitem",
            model=camera.model or camera.type or None,
            via_device_id=coordinator.panel_device_id,
        )
        if camera.name:
            self._attr_device_info["name"] = camera.name
        else:
            self._attr_device_info["translation_key"] = "camera"
            self._attr_device_info["translation_placeholders"] = {"id": str(camera.id)}

    def _camera(self) -> Camera | None:
        cameras = self.coordinator.data.cameras if self.coordinator.data else []
        return next((c for c in cameras if c.id == self._camera_id), None)

    @property
    def available(self) -> bool:
        return super().available and self._camera() is not None

    @property
    def native_value(self) -> str | None:
        camera = self._camera()
        return camera.status if camera else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        camera = self._camera()
        return {"type": camera.type} if camera else {}


class DaitemLastClip(DaitemEntity, SensorEntity):
    """When the latest recorded clip was taken, and what it is."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_clip"

    def __init__(self, coordinator: DaitemCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.system_id}_last_clip"

    @property
    def native_value(self) -> datetime | None:
        clip = self.coordinator.data.latest_clip if self.coordinator.data else None
        return clip.taken_at if clip else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        clip = self.coordinator.data.latest_clip if self.coordinator.data else None
        if clip is None:
            return {"clips": 0}
        return {
            "clips": len(self.coordinator.data.clips) if self.coordinator.data else 0,
            "kind": clip.kind,
            "category": clip.category,
            "device_uid": clip.device_uid,
            "duration_s": clip.duration_ms / 1000 if clip.duration_ms is not None else None,
        }


class DaitemLastEvent(DaitemEventLogEntity, SensorEntity):
    """When the latest event log entry happened, with its title."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_event"

    def __init__(self, coordinator: DaitemEventLogCoordinator, system_id: int) -> None:
        super().__init__(coordinator, system_id)
        self._attr_unique_id = f"{system_id}_last_event"

    @property
    def native_value(self) -> datetime | None:
        entry = self.coordinator.data[0] if self.coordinator.data else None
        when = entry.when if entry else None
        if when is None:
            return None
        # The log gives local time without a zone: read it in Home Assistant's own zone.
        return when if when.tzinfo else when.replace(tzinfo=dt_util.get_default_time_zone())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        entry = self.coordinator.data[0] if self.coordinator.data else None
        return {"title": entry.title} if entry else {}
