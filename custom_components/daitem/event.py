"""The panel's event log as an event entity: one event per new entry.

Entries already in the log when Home Assistant starts are not replayed: only what appears
afterwards fires. Titles are translation keys of the Daitem app (`logEvent.36.label2`),
passed on as they are, with the details, in the event attributes.
"""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaitem import LogEntry

from .coordinator import DaitemConfigEntry
from .event_log import DaitemEventLogCoordinator
from .event_log_entity import DaitemEventLogEntity

#: Read-only platform: the coordinator drives refreshes on its own.
PARALLEL_UPDATES = 0

EVENT_TYPE = "logged"

#: At most this many events per read, so a long outage does not flood the event bus.
MAX_EVENTS_PER_READ = 20


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaitemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.event_log is not None:
        async_add_entities([DaitemEventLog(coordinator.event_log, coordinator.system_id)])


def _key(entry: LogEntry) -> tuple[str, str, str]:
    return entry.date, entry.title, repr(entry.details)


class DaitemEventLog(DaitemEventLogEntity, EventEntity):
    _attr_translation_key = "event_log"
    _attr_event_types = [EVENT_TYPE]

    def __init__(self, coordinator: DaitemEventLogCoordinator, system_id: int) -> None:
        super().__init__(coordinator, system_id)
        self._attr_unique_id = f"{system_id}_event_log"
        self._seen: tuple[str, str, str] | None = _key(coordinator.data[0]) if coordinator.data else None
        # A log read empty is a baseline too: what appears in it afterwards is new.
        self._baseline_read = coordinator.data is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        entries = self.coordinator.data
        if entries is not None:
            new: list[LogEntry] = []
            for entry in entries:
                if _key(entry) == self._seen:
                    break
                new.append(entry)
            if self._baseline_read:
                # Oldest first, so automations see them in the order they happened.
                for entry in reversed(new[:MAX_EVENTS_PER_READ]):
                    self._trigger_event(
                        EVENT_TYPE, {"date": entry.date, "title": entry.title, "details": entry.details}
                    )
            self._baseline_read = True
            if entries:
                self._seen = _key(entries[0])
        # Written on every update, so the availability follows the reads, new entries or not.
        self.async_write_ha_state()
