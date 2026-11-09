"""Automations (gates, garage doors, shutters, lights, plugs): one device each.

Which Home Assistant entity an automation becomes depends on its category and on the
commands it lists, since only those may be sent:

- a gate, garage door or shutter that can be told to open and close is a `cover`;
- one that only takes an impulse (`PULSE`, `SWITCH`) is a `button`, because it reports no
  state worth trusting (assumption A2 in the README);
- a light with ON and OFF is a `light`, anything else with ON and OFF a `switch`;
- anything else with an impulse is a `button`, and the rest is left out, with a log line.

None of this was checked against real hardware when it was written: the command and state
vocabulary comes from an analysis of the app's behaviour. The entities therefore declare
an assumed state, so the UI keeps both directions available whatever the state reads.
"""

from __future__ import annotations

import logging

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from pydaitem import (
    Automatism,
    AutomatismCategory,
    AutomatismCommand,
    DaitemError,
)

from .const import DOMAIN
from .coordinator import DaitemCoordinator
from .entity import DaitemEntity
from .errors import command_error, needs_reauth

_LOGGER = logging.getLogger(__name__)

OPENINGS = frozenset({AutomatismCategory.GATE, AutomatismCategory.GARAGE, AutomatismCategory.SHUTTER})
IMPULSES = (AutomatismCommand.PULSE, AutomatismCommand.SWITCH, AutomatismCommand.ON)


def entity_kind(automatism: Automatism) -> str | None:
    """The platform an automation belongs to, or None when nothing fits."""
    commands = set(automatism.available_commands)
    on_off = {AutomatismCommand.ON, AutomatismCommand.OFF} <= commands
    up_down = {AutomatismCommand.UP, AutomatismCommand.DOWN} <= commands
    if automatism.category in OPENINGS:
        if up_down or on_off or AutomatismCommand.POSITION in commands:
            return "cover"
        if commands & {AutomatismCommand.PULSE, AutomatismCommand.SWITCH}:
            return "button"
        return None
    if on_off:
        return "light" if automatism.category == AutomatismCategory.LIGHT else "switch"
    if commands & set(IMPULSES):
        return "button"
    return None


def automatisms_for(coordinator: DaitemCoordinator, kind: str) -> list[Automatism]:
    """The automations a platform creates entities for, logging those no platform takes."""
    automatisms = coordinator.data.automatisms if coordinator.data else []
    if kind == "button":
        for automatism in automatisms:
            if entity_kind(automatism) is None:
                _LOGGER.info(
                    "Automation %s (%s) has no entity: its commands %s fit none. Please "
                    "report it with the diagnostics.",
                    automatism.label or automatism.id,
                    automatism.category,
                    automatism.available_commands,
                )
    return [a for a in automatisms if entity_kind(a) == kind]


def first_accepted(automatism: Automatism, *candidates: str) -> str | None:
    return next((c for c in candidates if automatism.accepts(c)), None)


class DaitemAutomatismEntity(DaitemEntity):
    """The main entity of one automation's device."""

    _attr_name = None
    _attr_assumed_state = True

    def __init__(self, coordinator: DaitemCoordinator, automatism: Automatism) -> None:
        super().__init__(coordinator)
        self._automatism_id = automatism.id
        key = f"{coordinator.system_id}_automatism_{automatism.id}"
        self._attr_unique_id = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, key)},
            manufacturer="Daitem",
            name=automatism.label or f"{automatism.category.title()} {automatism.id}",
            model=automatism.category,
            via_device_id=coordinator.panel_device_id,
        )

    def current(self) -> Automatism | None:
        """The automation as of the latest read, or None once it is gone."""
        return self.coordinator.data.automatism(self._automatism_id) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self.current() is not None

    async def _send(self, command: str | None, *, position: int | None = None) -> None:
        automatism = self.current()
        if automatism is None or command is None:
            raise HomeAssistantError("This automation cannot do that right now.")
        try:
            await self.coordinator.system.automation.command(automatism, command, position=position)
        except DaitemError as err:
            if needs_reauth(err):
                self.coordinator.config_entry.async_start_reauth(self.hass)
            raise command_error(err) from err
        self.coordinator.async_follow_up_command()
