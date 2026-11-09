"""Lights driven through the alarm."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaitem import AutomatismCommand

from .automatism import DaitemAutomatismEntity, automatisms_for
from .coordinator import DaitemConfigEntry

#: One command at a time: the panel takes a single session.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaitemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DaitemLight(coordinator, a) for a in automatisms_for(coordinator, "light"))


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
