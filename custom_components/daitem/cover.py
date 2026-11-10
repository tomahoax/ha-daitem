"""Gates, garage doors and shutters that can be told to open and close.

OFF reads closed, ON open, and a POSITION state carries a position from 0 (closed) to 100
(open), as the README says. The entity declares an assumed state, so both directions stay
available whatever the state reads.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaitem import Automatism, AutomatismCategory, AutomatismCommand, AutomatismStateType

from .automatism import DaitemAutomatismEntity, async_track_automations, first_accepted
from .coordinator import DaitemConfigEntry, DaitemCoordinator

#: One command at a time: the panel takes a single session.
PARALLEL_UPDATES = 1

DEVICE_CLASSES = {
    AutomatismCategory.GATE: CoverDeviceClass.GATE,
    AutomatismCategory.GARAGE: CoverDeviceClass.GARAGE,
    AutomatismCategory.SHUTTER: CoverDeviceClass.SHUTTER,
}

OPEN = (AutomatismCommand.UP, AutomatismCommand.ON)
CLOSE = (AutomatismCommand.DOWN, AutomatismCommand.OFF)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaitemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_track_automations(entry, "cover", DaitemCover, async_add_entities)


class DaitemCover(DaitemAutomatismEntity, CoverEntity):
    """One opening driven through the alarm."""

    def __init__(self, coordinator: DaitemCoordinator, automatism: Automatism) -> None:
        super().__init__(coordinator, automatism)
        self._attr_device_class = DEVICE_CLASSES.get(automatism.category)  # type: ignore[call-overload]
        features = CoverEntityFeature(0)
        positional = automatism.accepts(AutomatismCommand.POSITION)
        if first_accepted(automatism, *OPEN) or positional:
            features |= CoverEntityFeature.OPEN
        if first_accepted(automatism, *CLOSE) or positional:
            features |= CoverEntityFeature.CLOSE
        if automatism.accepts(AutomatismCommand.STOP):
            features |= CoverEntityFeature.STOP
        if positional:
            features |= CoverEntityFeature.SET_POSITION
        self._attr_supported_features = features

    @property
    def is_closed(self) -> bool | None:
        automatism = self.current()
        if automatism is None:
            return None
        if automatism.state == AutomatismStateType.POSITION and automatism.position is not None:
            return automatism.position == 0
        return None if automatism.is_on is None else not automatism.is_on

    @property
    def current_cover_position(self) -> int | None:
        automatism = self.current()
        if automatism is None or automatism.state != AutomatismStateType.POSITION:
            return None
        return automatism.position

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._move(OPEN, 100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._move(CLOSE, 0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._send(AutomatismCommand.STOP)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._send(AutomatismCommand.POSITION, position=int(kwargs[ATTR_POSITION]))

    async def _move(self, commands: tuple[str, ...], position: int) -> None:
        automatism = self.current()
        command = first_accepted(automatism, *commands) if automatism else None
        if command is None and automatism is not None and automatism.accepts(AutomatismCommand.POSITION):
            await self._send(AutomatismCommand.POSITION, position=position)
            return
        await self._send(command)
