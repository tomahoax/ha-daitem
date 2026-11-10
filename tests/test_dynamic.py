"""What the Daitem app gains after setup appears in Home Assistant without a reload.

Home Assistant's `dynamic-devices` rule: a detector learnt by the installer, an automation,
a scenario or a camera added in the app gets its entities on the next cycle that reads it.
"""

from __future__ import annotations

import copy
import logging
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pydaitem import Automatism, Camera, Extras, Inventory, Scenario
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA, INVENTORY_PAYLOAD
from custom_components.daitem.const import DOMAIN

SHUTTER = Automatism.from_json(
    {"id": "s1", "label": "Salon", "category": "SHUTTER", "availableCommands": ["UP", "DOWN", "STOP"]}
)
SPRINKLER = Automatism.from_json(
    {"id": "x9", "label": "Arrosage", "category": "UNKNOW", "availableCommands": ["TIMER"]}
)
CAMERA = Camera.from_json({"id": 3, "name": "Jardin", "type": "DAHUA", "status": "ONLINE"})
NIGHT = Scenario.from_json({"id": 7, "name": "Night", "active": True, "triggerType": "MANUAL"})


@pytest.fixture
async def entry(hass: HomeAssistant, mock_client: AsyncMock) -> MockConfigEntry:
    config_entry = MockConfigEntry(domain=DOMAIN, title="Home", data=ENTRY_DATA, unique_id="123456")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _next_cycle(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """A cycle that reads everything again, whatever its own pace."""
    coordinator = entry.runtime_data
    coordinator._extras_due = 0.0
    coordinator._scenarios_due = 0.0
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_an_automation_added_in_the_app_appears(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    assert hass.states.get("cover.salon") is None
    mock_client.system.read_extras.return_value = Extras(automatisms=[SHUTTER], cameras=[], clips=[])
    await _next_cycle(hass, entry)
    assert hass.states.get("cover.salon") is not None


async def test_a_camera_added_in_the_app_appears_with_the_clip_sensor(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    assert hass.states.get("sensor.alarm_panel_home_latest_clip") is None
    mock_client.system.read_extras.return_value = Extras(automatisms=[], cameras=[CAMERA], clips=[])
    await _next_cycle(hass, entry)
    assert hass.states.get("sensor.jardin_camera_status").state == "ONLINE"
    assert hass.states.get("sensor.alarm_panel_home_latest_clip") is not None


async def test_a_scenario_added_in_the_app_appears(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.system.scenarios.read.return_value = [NIGHT]
    await _next_cycle(hass, entry)
    assert hass.states.get("button.alarm_panel_home_scenario_night") is not None


async def test_a_detector_learnt_later_appears(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    payload = copy.deepcopy(INVENTORY_PAYLOAD)
    payload["genericSensors"]["sensors"] = [
        {"index": 5, "name": "Veranda", "serialNumber": "SN-5", "group": 3, "anomalies": {"radioAlert": False}}
    ]
    mock_client.system.inventory.read.return_value = Inventory.from_json(payload)
    await _next_cycle(hass, entry)
    assert hass.states.get("binary_sensor.veranda_radio") is not None
    assert hass.states.get("sensor.veranda_group").state == "3"


async def test_nothing_is_added_twice(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """The same automation read on every cycle keeps its one entity, and its one log line."""
    mock_client.system.read_extras.return_value = Extras(automatisms=[SHUTTER, SPRINKLER], cameras=[], clips=[])
    with caplog.at_level(logging.INFO):
        await _next_cycle(hass, entry)
        await _next_cycle(hass, entry)

    entities = [e for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id) if "s1" in e.unique_id]
    assert len(entities) == 1
    assert caplog.text.count("Automation Arrosage (UNKNOW) has no entity") == 1
