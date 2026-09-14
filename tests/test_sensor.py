"""Firmware versions and group membership, the read-only facts taken from the inventory."""

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

FIRMWARE_ENTITIES = {
    "sensor.alarm_panel_home_main_software": "6.4.13",
    "sensor.alarm_panel_home_radio_firmware": "15",
    "sensor.alarm_panel_home_transmission_module": "7.8.4",
}


@pytest.mark.parametrize(("entity_id", "version"), FIRMWARE_ENTITIES.items())
async def test_each_firmware_version_is_reported(
    hass: HomeAssistant, entry: MockConfigEntry, entity_id: str, version: str
) -> None:
    """The three versions the mobile app shows, from the payload that always carried them."""
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == version


async def test_firmware_sensors_stay_out_of_the_way(
    hass: HomeAssistant, entry: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """A version number is looked up once, it does not deserve a dashboard row."""
    for entity_id in FIRMWARE_ENTITIES:
        registered = entity_registry.async_get(entity_id)
        assert registered is not None
        assert registered.hidden_by is er.RegistryEntryHider.INTEGRATION
        assert registered.entity_category is er.EntityCategory.DIAGNOSTIC


async def test_the_main_software_also_reaches_the_device_page(
    hass: HomeAssistant, entry: MockConfigEntry, device_registry: dr.DeviceRegistry
) -> None:
    """Two registry fields cannot hold three versions, so only the main one goes there."""
    panel = device_registry.async_get_device_by_identifier((DOMAIN, "123456"), entry.entry_id)
    assert panel is not None
    assert panel.sw_version == "6.4.13"


async def test_a_panel_reporting_no_firmware_gets_no_sensors(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Absent must stay absent rather than three entities stuck on unknown forever."""
    payload = copy.deepcopy(INVENTORY_PAYLOAD)
    del payload["central"]["firmwareInfo"]
    del payload["central"]["plug"]["firmwareInfo"]
    mock_client.system.read_inventory.return_value = Inventory.from_json(payload)

    other = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="bare")
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.alarm_panel_annexe_main_software") is None
    assert hass.states.get("sensor.alarm_panel_annexe_radio_firmware") is None


async def test_only_detectors_carry_a_group(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Controls report no group at all on a live panel, so they get no group sensor."""
    payload = copy.deepcopy(INVENTORY_PAYLOAD)
    payload["genericSensors"]["sensors"] = [
        {"index": 1, "name": "Kitchen", "serialNumber": "SN-D1", "group": 2, "anomalies": {}}
    ]
    payload["commands"] = [{"index": 1, "name": "Keypad", "serialNumber": "SN-C1", "isInhibitable": True}]
    mock_client.system.read_inventory.return_value = Inventory.from_json(payload)

    other = MockConfigEntry(domain=DOMAIN, title="Chalet", data=ENTRY_DATA, unique_id="grouped")
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.kitchen_group").state == "2"
    assert hass.states.get("sensor.keypad_group") is None


async def test_the_alarm_entity_lists_what_each_group_contains(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """A mapping alongside `active_groups`, so a group number can be read as a place."""
    payload = copy.deepcopy(INVENTORY_PAYLOAD)
    payload["genericSensors"]["sensors"] = [
        {"index": 1, "name": "Garage Door", "serialNumber": "SN-1", "group": 1, "anomalies": {}},
        {"index": 2, "name": "Kitchen Radar", "serialNumber": "SN-2", "group": 2, "anomalies": {}},
        {"index": 3, "name": "Front Door", "serialNumber": "SN-3", "group": 1, "anomalies": {}},
    ]
    mock_client.system.read_inventory.return_value = Inventory.from_json(payload)

    other = MockConfigEntry(domain=DOMAIN, title="Mas", data=ENTRY_DATA, unique_id="mapping")
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()

    groups = hass.states.get("alarm_control_panel.alarm_panel_mas").attributes["groups"]
    # Keys are strings: a state attribute is serialised to JSON, where integer keys
    # would not survive anyway.
    assert groups == {"1": ["Front Door", "Garage Door"], "2": ["Kitchen Radar"]}


async def test_the_group_mapping_reads_like_the_device_pages(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Ordered by number, and an unnamed detector called what its device page calls it.

    Sorting the keys as strings would put group 10 before group 2, and taking `name` raw
    would list an unnamed detector as a blank the reader cannot match to anything.
    """
    payload = copy.deepcopy(INVENTORY_PAYLOAD)
    payload["genericSensors"]["sensors"] = [
        {"index": 1, "name": "Cellar", "serialNumber": "SN-1", "group": 10, "anomalies": {}},
        {"index": 2, "name": "", "serialNumber": "SN-2", "group": 2, "anomalies": {}},
    ]
    mock_client.system.read_inventory.return_value = Inventory.from_json(payload)

    other = MockConfigEntry(domain=DOMAIN, title="Ferme", data=ENTRY_DATA, unique_id="ordering")
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()

    groups = hass.states.get("alarm_control_panel.alarm_panel_ferme").attributes["groups"]
    assert list(groups) == ["2", "10"]
    assert groups["2"] == ["Detector 2"]
