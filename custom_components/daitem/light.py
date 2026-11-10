"""Lights driven through the alarm."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaitem import AutomatismCommand

from .automatism import DaitemAutomatismEntity, async_track_automations
from .coordinator import DaitemConfigEntry

#: One command at a time: the panel takes a single session.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaitemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_track_automations(entry, "light", DaitemLight, async_add_entities)


class DaitemLight(DaitemAutomatismEntity, LightEntity):
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    @property
    def is_on(self) -> bool | None:
        automatism = self.current()
        return automatism.is_on if automatism else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(AutomatismCommand.ON)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(AutomatismCommand.OFF)
