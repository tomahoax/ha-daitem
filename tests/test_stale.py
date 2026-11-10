"""Deleting by hand a device the Daitem app no longer lists (Home Assistant's `stale-devices`).

Nothing is deleted on its own: a device's rename, area and entities would go with it. The
delete button is allowed only once Daitem was read and no longer lists the device.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pydaitem import Automatism, DaitemError, Extras, Inventory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA, INVENTORY_PAYLOAD
from custom_components.daitem import async_remove_config_entry_device
from custom_components.daitem.const import DOMAIN

SID = ENTRY_DATA["system_id"]
GATE = Automatism.from_json({"id": "g1", "label": "Portail", "category": "GATE", "availableCommands": ["PULSE"]})
WITH_GATE = Extras(automatisms=[GATE], cameras=[], clips=[])
EMPTY = Extras(automatisms=[], cameras=[], clips=[])


def _inventory(*, with_detector: bool) -> Inventory:
    payload = copy.deepcopy(INVENTORY_PAYLOAD)
    if with_detector:
        payload["genericSensors"]["sensors"] = [
            {"index": 1, "name": "Hall", "serialNumber": "SN-1", "anomalies": {"radioAlert": False}}
        ]
    return Inventory.from_json(payload)


@pytest.fixture
async def entry(hass: HomeAssistant, mock_client: AsyncMock) -> MockConfigEntry:
    mock_client.system.inventory.read.return_value = _inventory(with_detector=True)
    mock_client.system.read_extras.return_value = WITH_GATE
    config_entry = MockConfigEntry(domain=DOMAIN, title="Home", data=ENTRY_DATA, unique_id=str(SID))
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _cycle(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.runtime_data._extras_due = 0.0
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def _device(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> dr.DeviceEntry:
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, key), entry.entry_id)
    assert device is not None, key
    return device


async def _may_delete(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> bool:
    return await async_remove_config_entry_device(hass, entry, _device(hass, entry, key))


async def test_the_panel_and_listed_devices_cannot_be_deleted(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert not await _may_delete(hass, entry, str(SID))
    assert not await _may_delete(hass, entry, f"{SID}_automatism_g1")
    assert not await _may_delete(hass, entry, f"{SID}_sensor_1")


async def test_a_device_gone_from_the_app_can_be_deleted(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.system.read_extras.return_value = EMPTY
    mock_client.system.inventory.read.return_value = _inventory(with_detector=False)
    await _cycle(hass, entry)

    assert await _may_delete(hass, entry, f"{SID}_automatism_g1")
    assert await _may_delete(hass, entry, f"{SID}_sensor_1")


async def test_an_outage_is_not_taken_for_a_removal(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.system.read_extras.return_value = Extras(
        automatisms=None, cameras=[], clips=[], errors={"automatisms": DaitemError("down")}
    )
    mock_client.system.inventory.read.side_effect = DaitemError("down")
    await _cycle(hass, entry)

    assert not await _may_delete(hass, entry, f"{SID}_automatism_g1")
    assert not await _may_delete(hass, entry, f"{SID}_sensor_1")


async def test_a_deleted_device_that_comes_back_gets_its_entities_again(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.system.read_extras.return_value = EMPTY
    await _cycle(hass, entry)
    device = _device(hass, entry, f"{SID}_automatism_g1")
    assert await async_remove_config_entry_device(hass, entry, device)
    # What Home Assistant does once the integration allows it.
    dr.async_get(hass).async_remove_device(device.id)
    await hass.async_block_till_done()
    assert hass.states.get("button.portail") is None

    mock_client.system.read_extras.return_value = WITH_GATE
    await _cycle(hass, entry)
    assert hass.states.get("button.portail") is not None
