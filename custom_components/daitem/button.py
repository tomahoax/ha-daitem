"""Manual refresh button for the alarm state."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DaitemConfigEntry, DaitemCoordinator
from .entity import DaitemEntity

#: The coordinator drives refreshes on its own.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaitemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([DaitemRefreshButton(entry.runtime_data)])


class DaitemRefreshButton(DaitemEntity, ButtonEntity):
    """Force an immediate state read instead of waiting for the next cycle."""

    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_visible_default = False

    def __init__(self, coordinator: DaitemCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.system_id}_refresh"

    async def async_press(self) -> None:
        # Debounced by the coordinator, so repeated presses will not pile up sessions
        # on the panel.
        await self.coordinator.async_request_refresh()
