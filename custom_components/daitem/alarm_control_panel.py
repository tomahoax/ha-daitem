"""Alarm control panel entity for Daitem."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pydaitem import ArmMode, DaitemError, DaitemSessionBusyError, Inventory, PanelState, SystemStatus

from .coordinator import DaitemConfigEntry, DaitemCoordinator
from .entity import DaitemEntity

#: Commands are serialised: the panel accepts one session at a time, so two concurrent
#: commands would collide.
PARALLEL_UPDATES = 1

#: Library states mapped onto Home Assistant ones.
#:
#: This maps from `PanelState`, the library's own stable vocabulary, not from raw API
#: strings. A change in the Daitem API is absorbed by the library, leaving this untouched.
#: `UNKNOWN` is deliberately absent so it surfaces as an unknown entity state.
#: Partial-arming raw states (armed via a named preset or a direct group command) are
#: deliberately absent: which preset means what is a guess pydaitem cannot verify beyond
#: "presence" (matched by its technical key), so it is not shown as Night/Vacation here.
#: It surfaces as an honest `unknown` rather than a label that might be wrong.
STATE_MAP: dict[PanelState, AlarmControlPanelState] = {
    PanelState.DISARMED: AlarmControlPanelState.DISARMED,
    PanelState.ARMING: AlarmControlPanelState.ARMING,
    PanelState.ARMED_FULL: AlarmControlPanelState.ARMED_AWAY,
    PanelState.ARMED_PRESENCE: AlarmControlPanelState.ARMED_HOME,
    PanelState.TRIGGERED: AlarmControlPanelState.TRIGGERED,
}

#: Which Home Assistant feature each library arming mode unlocks. Only the modes whose
#: meaning is verifiable: Away is the base command, Presence is confirmed by its
#: technical key. Partial presets are intentionally not offered here, see STATE_MAP.
FEATURE_MAP: dict[ArmMode, AlarmControlPanelEntityFeature] = {
    ArmMode.AWAY: AlarmControlPanelEntityFeature.ARM_AWAY,
    ArmMode.PRESENCE: AlarmControlPanelEntityFeature.ARM_HOME,
}


def _group_membership(inventory: Inventory | None) -> dict[str, list[str]]:
    """Which detectors each group contains, alongside `active_groups`.

    Keyed by group number as a string, because state attributes are serialised to JSON and
    an integer key would not survive anyway. The API gives numbers and no names: no group
    name appears in the inventory, and none has ever been observed in the state payload.
    """
    if inventory is None:
        return {}
    membership: dict[str, list[str]] = {}
    for device in inventory.devices:
        if device.group is None:
            continue
        membership.setdefault(str(device.group), []).append(device.name)
    return {group: sorted(names) for group, names in sorted(membership.items())}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaitemConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([DaitemAlarmPanel(entry.runtime_data)])


class DaitemAlarmPanel(DaitemEntity, AlarmControlPanelEntity):
    """The alarm control panel."""

    _attr_name = None
    _attr_code_arm_required = False

    def __init__(self, coordinator: DaitemCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.system_id}_alarm"

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        """Advertise only the modes this installation actually supports.

        Read on every state write rather than frozen at construction: discovery can be
        blocked at setup by a session another device holds, and the coordinator retries
        it. The Home button then comes back on its own, without a reload.
        """
        features = AlarmControlPanelEntityFeature(0)
        for mode in self.coordinator.arm_modes:
            features |= FEATURE_MAP.get(mode, AlarmControlPanelEntityFeature(0))
        return features

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        data = self.coordinator.data
        if data is None:
            return None
        return STATE_MAP.get(data.status.panel_state)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "panel_state": data.status.panel_state.value,
            "active_groups": data.status.active_groups,
            "groups": _group_membership(data.inventory),
            "last_successful_update": data.last_success.isoformat(),
            # True when another device holds the session: the values shown are then the
            # last known state.
            "session_busy": data.session_busy,
        }

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self._run(self.coordinator.system.commands.disarm)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self._run(self.coordinator.system.commands.arm_away)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        await self._run(self.coordinator.system.commands.arm_presence)

    async def _run(self, action: Callable[[], Awaitable[SystemStatus]]) -> None:
        """Run one command and publish the state it returns.

        Session handling lives in the library: the integration only says what it wants.
        """
        try:
            status = await action()
        except DaitemSessionBusyError as err:
            raise HomeAssistantError(
                "The alarm is already being controlled by another device. Close the "
                "Daitem app on your phone and try again."
            ) from err
        except DaitemError as err:
            raise HomeAssistantError(f"Daitem command rejected: {err}") from err

        await self.coordinator.async_apply_command_result(status)
