"""Per-device entities: detectors, controls, and the identity that separates them.

Controls (remotes, keypads) were invisible until now. They come from the same inventory
section shape as detectors but are numbered in their own list, which is the trap this file
mostly exists to guard.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pydaitem import Inventory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA, INVENTORY_PAYLOAD
from custom_components.daitem.const import DOMAIN

#: `system_id` comes from the panel the library reports, not from the config entry.
PANEL_KEY = "123456"
DETECTOR_KEY = f"{PANEL_KEY}_sensor_1"
CONTROL_KEY = f"{PANEL_KEY}_command_1"

DETECTOR_ANOMALIES = {
    "powerSupplyAlert": False,
    "radioAlert": False,
    "maskAlert": False,
    "sensorAlert": False,
    "loopAlert": False,
    "autoprotectionMechanicalAlert": False,
}


def _payload() -> dict:
    """One detector and one control, both at index 1, as a live panel really reports."""
    payload = copy.deepcopy(INVENTORY_PAYLOAD)
    payload["genericSensors"]["sensors"] = [
        {
            "index": 1,
            "name": "Front Door",
            "serialNumber": "SN-D1",
            "type": "DEFAULT",
            "group": 1,
            "isInhibitable": True,
            "isInhibited": False,
            "anomalies": DETECTOR_ANOMALIES,
        }
    ]
    # No group, and an empty anomalies block: exactly what a control returns.
    payload["commands"] = [
        {
            "index": 1,
            "name": "Remote 1",
            "serialNumber": "SN-C1",
            "type": "REMOTE",
            "isInhibitable": True,
            "isInhibited": True,
            "anomalies": {},
        }
    ]
    return payload


@pytest.fixture
async def populated(hass: HomeAssistant, mock_client: AsyncMock) -> MockConfigEntry:
    mock_client.system.read_inventory.return_value = Inventory.from_json(_payload())
    entry = MockConfigEntry(domain=DOMAIN, title="Villa", data=ENTRY_DATA, unique_id="villa")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_a_detector_and_a_control_sharing_an_index_stay_separate(
    hass: HomeAssistant, populated: MockConfigEntry, device_registry: dr.DeviceRegistry
) -> None:
    """Indices are numbered per list, so index 1 exists twice on any real installation.

    Without the kind in the identifier the two would collapse into one device and their
    entities would fight over the same unique ids.
    """
    detector = device_registry.async_get_device_by_identifier((DOMAIN, DETECTOR_KEY), populated.entry_id)
    control = device_registry.async_get_device_by_identifier((DOMAIN, CONTROL_KEY), populated.entry_id)

    assert detector is not None
    assert control is not None
    assert detector.id != control.id
    assert detector.name == "Front Door"
    assert control.name == "Remote 1"


async def test_both_hang_off_the_panel(
    hass: HomeAssistant, populated: MockConfigEntry, device_registry: dr.DeviceRegistry
) -> None:
    panel = device_registry.async_get_device_by_identifier((DOMAIN, PANEL_KEY), populated.entry_id)
    assert panel is not None
    for identifier in (DETECTOR_KEY, CONTROL_KEY):
        device = device_registry.async_get_device_by_identifier((DOMAIN, identifier), populated.entry_id)
        assert device is not None
        assert device.via_device_id == panel.id


async def test_a_control_is_not_an_empty_device(
    hass: HomeAssistant, populated: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """A control reports no fault, so inhibition is what keeps its device alive.

    Home Assistant prunes a device that carries no entity, so without this the four remotes
    and keypads of a real installation would appear and then vanish.
    """
    state = hass.states.get("binary_sensor.remote_1_inhibited")
    assert state is not None
    assert state.state == "on"

    entities = er.async_entries_for_device(entity_registry, entity_registry.async_get(state.entity_id).device_id)
    assert [e.unique_id for e in entities] == [f"{CONTROL_KEY}_inhibited"]


async def test_inhibition_is_visible_without_going_looking_for_it(
    hass: HomeAssistant, populated: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """Unlike the faults, a neutralised detector is not hidden behind a toggle."""
    entry = entity_registry.async_get("binary_sensor.front_door_inhibited")
    assert entry is not None
    assert entry.hidden_by is None

    assert hass.states.get("binary_sensor.front_door_inhibited").state == "off"


async def test_a_control_reports_no_fault_sensor(
    hass: HomeAssistant, populated: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """Its anomalies block is empty on a live panel, so no fault entity must be invented."""
    assert hass.states.get("binary_sensor.remote_1_battery") is None
    assert hass.states.get("binary_sensor.remote_1_radio") is None
    # The detector, which does report them, still gets its own.
    assert hass.states.get("binary_sensor.front_door_battery") is not None
