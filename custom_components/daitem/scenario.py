"""Scenarios the installer set up, as buttons: one per scenario run by hand.

Scenarios triggered by the panel itself (on fire, on intrusion) get none. A scenario runs
the actions it was given, which may arm or disarm the alarm, exactly as from the app.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaitem import DaitemError, Scenario

from .const import DOMAIN
from .coordinator import DaitemConfigEntry, DaitemCoordinator, DaitemData
from .entity import DaitemEntity, async_track_new
from .errors import command_error, needs_reauth
from .keys import scenario_key

#: `Scenario.trigger` of the scenarios a person runs. The others are the panel's to run.
MANUAL = "MANUAL"


def async_track_scenarios(entry: DaitemConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """A button per scenario run by hand, now and for each one added in the app later."""
    coordinator = entry.runtime_data

    def items(data: DaitemData) -> dict[str, Scenario]:
        return {scenario_key(coordinator.system_id, s): s for s in data.scenarios if s.trigger == MANUAL}

    async_track_new(
        entry, "button.scenarios", items, lambda s: [DaitemScenarioButton(coordinator, s)], async_add_entities
    )


class DaitemScenarioButton(DaitemEntity, ButtonEntity):
    """Run one scenario. Unavailable while the installer has it switched off."""

    _attr_translation_key = "scenario"

    def __init__(self, coordinator: DaitemCoordinator, scenario: Scenario) -> None:
        super().__init__(coordinator)
        self._scenario_id = scenario.id
        self._attr_unique_id = scenario_key(coordinator.system_id, scenario)
        self._attr_translation_placeholders = {"scenario_name": scenario.name or str(scenario.id)}

    def current(self) -> Scenario | None:
        return self.coordinator.data.scenario(self._scenario_id) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        scenario = self.current()
        return super().available and scenario is not None and scenario.active

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        scenario = self.current()
        return {"actions": len(scenario.actions)} if scenario else {}

    async def async_press(self) -> None:
        scenario = self.current()
        if scenario is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="scenario_gone")
        try:
            status = await self.coordinator.system.scenarios.run(scenario)
        except DaitemError as err:
            if needs_reauth(err):
                self.coordinator.config_entry.async_start_reauth(self.hass)
            raise command_error(err) from err
        await self.coordinator.async_apply_command_result(status)
