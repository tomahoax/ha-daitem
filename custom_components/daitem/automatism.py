"""Automations (gates, garage doors, shutters, lights, plugs): one device each.

Which Home Assistant entity an automation becomes depends on its category and on the
commands it lists, since only those may be sent:

- a gate, garage door or shutter that can be told to open and close is a `cover`;
- one that only takes an impulse (`PULSE`, `SWITCH`) is a `button`, because it reports no
  state worth trusting (see the README);
- a light with ON and OFF is a `light`, anything else with ON and OFF a `switch`;
- anything else with an impulse is a `button`, and the rest is left out, with a log line.

The entities declare an assumed state, so the UI keeps both directions available whatever
the state reads.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaitem import (
    Automatism,
    AutomatismCategory,
    AutomatismCommand,
    DaitemError,
)

from .const import DOMAIN
from .coordinator import DaitemConfigEntry, DaitemCoordinator, DaitemData
from .entity import DaitemEntity, async_track_new
from .errors import command_error, needs_reauth
from .keys import automation_key

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


def automation_translation_key(automatism: Automatism) -> str:
    """The device name key of an unlabelled automation: one per category, a generic one else."""
    known = {str(category) for category in AutomatismCategory}
    category = automatism.category if automatism.category in known else AutomatismCategory.UNKNOWN
    return f"automation_{AutomatismCategory(category).name.lower()}"


def async_track_automations(
    entry: DaitemConfigEntry,
    kind: str,
    factory: Callable[[DaitemCoordinator, Automatism], Entity],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Give each automation of this platform's kind its entity, now and when one is added."""
    coordinator = entry.runtime_data

    def items(data: DaitemData) -> dict[str, Automatism]:
        return {automation_key(coordinator.system_id, a): a for a in data.automatisms if entity_kind(a) == kind}

    async_track_new(entry, f"{kind}.automations", items, lambda a: [factory(coordinator, a)], async_add_entities)


def async_report_unmapped_automations(
    entry: DaitemConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Log, once per automation, those whose commands fit no entity."""
    coordinator = entry.runtime_data

    def items(data: DaitemData) -> dict[str, Automatism]:
        return {automation_key(coordinator.system_id, a): a for a in data.automatisms if entity_kind(a) is None}

    def report(automatism: Automatism) -> list[Entity]:
        _LOGGER.info(
            "Automation %s (%s) has no entity: its commands %s fit none. Please report it with the diagnostics.",
            automatism.label or automatism.id,
            automatism.category,
            automatism.available_commands,
        )
        return []

    async_track_new(entry, "unmapped.automations", items, report, async_add_entities)


def first_accepted(automatism: Automatism, *candidates: str) -> str | None:
    return next((c for c in candidates if automatism.accepts(c)), None)


class DaitemAutomatismEntity(DaitemEntity):
    """The main entity of one automation's device."""

    _attr_name = None
    _attr_assumed_state = True

    def __init__(self, coordinator: DaitemCoordinator, automatism: Automatism) -> None:
        super().__init__(coordinator)
        self._automatism_id = automatism.id
        key = automation_key(coordinator.system_id, automatism)
        self._attr_unique_id = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, key)},
            manufacturer="Daitem",
            model=automatism.category,
            via_device_id=coordinator.panel_device_id,
        )
        if automatism.label:
            self._attr_device_info["name"] = automatism.label
        else:
            # Named by Home Assistant in its own language, after what the automation drives.
            self._attr_device_info["translation_key"] = automation_translation_key(automatism)
            self._attr_device_info["translation_placeholders"] = {"id": automatism.id}

    def current(self) -> Automatism | None:
        """The automation as of the latest read, or None once it is gone."""
        return self.coordinator.data.automatism(self._automatism_id) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self.current() is not None

    async def _send(self, command: str | None, *, position: int | None = None) -> None:
        automatism = self.current()
        if automatism is None or command is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="command_not_available")
        try:
            await self.coordinator.system.automation.command(automatism, command, position=position)
        except DaitemError as err:
            if needs_reauth(err):
                self.coordinator.config_entry.async_start_reauth(self.hass)
            raise command_error(err) from err
        self.coordinator.async_follow_up_command()
