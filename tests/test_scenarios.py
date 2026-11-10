"""Scenarios run by hand, as buttons.

Their read may hold the panel, so it is rare and skipped where it cannot pay: the tests
below pin that as much as the buttons themselves.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pydaitem import DaitemSessionBusyError, Inventory, PanelState, Scenario
from pydaitem.testing import status
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA, INVENTORY_PAYLOAD
from custom_components.daitem.const import DOMAIN
from custom_components.daitem.diagnostics import async_get_config_entry_diagnostics

NIGHT = Scenario.from_json(
    {"id": 7, "name": "Night", "active": True, "triggerType": "MANUAL", "actions": [{"type": "ARM"}]}
)
OFF = Scenario.from_json({"id": 8, "name": "Holidays", "active": False, "triggerType": "MANUAL"})
FIRE = Scenario.from_json({"id": 9, "name": "On fire", "active": True, "triggerType": "AUTO_FIRE"})

BUTTON = "button.alarm_panel_home_scenario_night"


async def _setup(hass: HomeAssistant, mock_client: AsyncMock, scenarios: list[Scenario]) -> MockConfigEntry:
    mock_client.system.scenarios.read.return_value = scenarios
    entry = MockConfigEntry(domain=DOMAIN, title="Home", data=ENTRY_DATA, unique_id="123456")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_a_manual_scenario_runs_and_publishes_the_state(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await _setup(hass, mock_client, [NIGHT])
    state = hass.states.get(BUTTON)
    assert state is not None
    assert state.attributes["actions"] == 1

    mock_client.system.scenarios.run.return_value = status(PanelState.ARMED_FULL)
    await hass.services.async_call(BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: BUTTON}, blocking=True)

    mock_client.system.scenarios.run.assert_awaited_once_with(NIGHT)
    assert hass.states.get("alarm_control_panel.alarm_panel_home").state == "armed_away"


async def test_only_scenarios_run_by_hand_get_a_button(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await _setup(hass, mock_client, [NIGHT, FIRE])
    buttons = [s.entity_id for s in hass.states.async_all(BUTTON_DOMAIN) if "scenario" in s.entity_id]
    assert buttons == [BUTTON]


async def test_a_scenario_switched_off_is_unavailable(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await _setup(hass, mock_client, [OFF])
    assert hass.states.get("button.alarm_panel_home_scenario_holidays").state == "unavailable"


async def test_a_failed_run_says_why(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await _setup(hass, mock_client, [NIGHT])
    mock_client.system.scenarios.run.side_effect = DaitemSessionBusyError("Phone")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: BUTTON}, blocking=True)
    assert err.value.translation_key == "session_busy"


async def test_an_installation_without_scenarios_is_not_asked(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    payload = copy.deepcopy(INVENTORY_PAYLOAD)
    payload["isScenarioEnabled"] = False
    mock_client.system.inventory.read.return_value = Inventory.from_json(payload)
    await _setup(hass, mock_client, [NIGHT])
    mock_client.system.scenarios.read.assert_not_called()
    assert hass.states.get(BUTTON) is None


async def test_scenarios_are_read_rarely(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Their read may hold the panel: once per thirty minutes, not once per cycle."""
    entry = await _setup(hass, mock_client, [NIGHT])
    await entry.runtime_data.async_refresh()
    await entry.runtime_data.async_refresh()
    mock_client.system.scenarios.read.assert_awaited_once()


async def test_scenarios_are_not_read_during_an_exit_delay(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    mock_client.system.panel.read.return_value = status(PanelState.ARMING)
    await _setup(hass, mock_client, [NIGHT])
    mock_client.system.scenarios.read.assert_not_called()


async def test_a_failed_read_keeps_the_buttons(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await _setup(hass, mock_client, [NIGHT])
    coordinator = entry.runtime_data
    coordinator._scenarios_due = 0.0
    mock_client.system.scenarios.read.side_effect = DaitemSessionBusyError("Phone")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data.scenarios == [NIGHT]
    assert hass.states.get(BUTTON).state != "unavailable"


async def test_diagnostics_list_the_scenarios_without_their_names(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await _setup(hass, mock_client, [NIGHT, FIRE])
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["extras"]["scenarios"] == [
        {"trigger": "MANUAL", "active": True, "actions": 1},
        {"trigger": "AUTO_FIRE", "active": True, "actions": 0},
    ]
    assert "Night" not in str(diagnostics["extras"])
