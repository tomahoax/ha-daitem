"""Plugs, and any other automation with ON and OFF that is not a light or an opening."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaitem import Automatism, AutomatismCategory, AutomatismCommand

from .automatism import DaitemAutomatismEntity, async_track_automations
from .coordinator import DaitemConfigEntry, DaitemCoordinator

#: One command at a time: the panel takes a single session.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaitemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_track_automations(entry, "switch", DaitemSwitch, async_add_entities)


class DaitemSwitch(DaitemAutomatismEntity, SwitchEntity):
    def __init__(self, coordinator: DaitemCoordinator, automatism: Automatism) -> None:
        super().__init__(coordinator, automatism)
        if automatism.category == AutomatismCategory.PLUG:
            self._attr_device_class = SwitchDeviceClass.OUTLET

    @property
    def is_on(self) -> bool | None:
        automatism = self.current()
        return automatism.is_on if automatism else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(AutomatismCommand.ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(AutomatismCommand.OFF)
