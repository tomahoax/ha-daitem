"""Manual refresh button for the alarm state, automations that only take an impulse, and
the scenarios run by hand."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaitem import Automatism

from .automatism import (
    IMPULSES,
    DaitemAutomatismEntity,
    async_report_unmapped_automations,
    async_track_automations,
    first_accepted,
)
from .coordinator import DaitemConfigEntry, DaitemCoordinator
from .entity import DaitemEntity
from .scenario import async_track_scenarios

#: One command at a time: the panel takes a single session.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaitemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([DaitemRefreshButton(entry.runtime_data)])
    async_track_automations(entry, "button", DaitemImpulseButton, async_add_entities)
    async_report_unmapped_automations(entry, async_add_entities)
    async_track_scenarios(entry, async_add_entities)


class DaitemRefreshButton(DaitemEntity, ButtonEntity):
    """Force an immediate state read instead of waiting for the next cycle."""

    _attr_translation_key = "refresh"
    # No entity category on purpose: pressing this acts on the panel, so it belongs with
    # the controls rather than among the read-only diagnostic entities.
    _attr_entity_registry_visible_default = False

    def __init__(self, coordinator: DaitemCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.system_id}_refresh"

    async def async_press(self) -> None:
        # Debounced by the coordinator, so repeated presses will not pile up sessions
        # on the panel.
        await self.coordinator.async_request_refresh()


class DaitemImpulseButton(DaitemAutomatismEntity, ButtonEntity):
    """A gate or garage door that only takes an impulse, so it has no trustworthy state."""

    def __init__(self, coordinator: DaitemCoordinator, automatism: Automatism) -> None:
        super().__init__(coordinator, automatism)

    async def async_press(self) -> None:
        automatism = self.current()
        await self._send(first_accepted(automatism, *IMPULSES) if automatism else None)
