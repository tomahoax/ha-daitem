"""Names Home Assistant gives what the Daitem app left unnamed, in the server's language.

The integration hard-codes no English name: an unnamed device carries a translation key,
and the device registry resolves it in the language Home Assistant runs in. A name given
in the app is the user's own and stays as it is.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import async_get_platforms
from pydaitem import Automatism, Camera, Extras, Inventory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA, INVENTORY_PAYLOAD
from custom_components.daitem.const import DOMAIN

SID = ENTRY_DATA["system_id"]


def _inventory() -> Inventory:
    payload = copy.deepcopy(INVENTORY_PAYLOAD)
    payload["genericSensors"]["sensors"] = [
        {"index": 3, "name": "", "serialNumber": "SN-3", "group": 2, "anomalies": {"radioAlert": False}},
        {"index": 4, "name": "Cellier", "serialNumber": "SN-4", "group": 2, "anomalies": {"radioAlert": False}},
    ]
    payload["sirens"] = [
        {"index": 1, "name": "", "serialNumber": "SN-S1", "isInhibitable": True, "anomalies": {}},
    ]
    return Inventory.from_json(payload)


GATE = Automatism.from_json({"id": "g1", "category": "GATE", "availableCommands": ["PULSE"]})
ODD = Automatism.from_json({"id": "x9", "category": "SPRINKLER", "availableCommands": ["PULSE"]})
CAMERA = Camera.from_json({"id": 3, "type": "DAHUA", "status": "ONLINE"})


async def _setup(hass: HomeAssistant, mock_client: AsyncMock, language: str) -> MockConfigEntry:
    hass.config.language = language
    mock_client.system.inventory.read.return_value = _inventory()
    mock_client.system.read_extras.return_value = Extras(automatisms=[GATE, ODD], cameras=[CAMERA], clips=[])
    entry = MockConfigEntry(domain=DOMAIN, title="Home", data=ENTRY_DATA, unique_id=str(SID))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _name(hass: HomeAssistant, key: str) -> str | None:
    device = next(
        (d for d in dr.async_get(hass).devices if (DOMAIN, key) in d.identifiers),
        None,
    )
    assert device is not None, key
    return device.name


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            "en",
            {
                f"{SID}_sensor_3": "Detector 3",
                f"{SID}_siren_1": "Siren 1",
                f"{SID}_automatism_g1": "Gate g1",
                f"{SID}_automatism_x9": "Automation x9",
                f"{SID}_camera_3": "Camera 3",
            },
        ),
        (
            "fr",
            {
                f"{SID}_sensor_3": "Détecteur 3",
                f"{SID}_siren_1": "Sirène 1",
                f"{SID}_automatism_g1": "Portail g1",
                f"{SID}_automatism_x9": "Automatisme x9",
                f"{SID}_camera_3": "Caméra 3",
            },
        ),
    ],
)
async def test_unnamed_devices_are_named_in_the_server_language(
    hass: HomeAssistant, mock_client: AsyncMock, language: str, expected: dict[str, str]
) -> None:
    await _setup(hass, mock_client, language)
    assert {key: _name(hass, key) for key in expected} == expected


async def test_a_name_from_the_app_is_kept_as_it_is(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await _setup(hass, mock_client, "fr")
    assert _name(hass, f"{SID}_sensor_4") == "Cellier"


async def test_the_group_attribute_reads_like_the_device_pages(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Translated names, and the user's own rename, reach the alarm's `groups` attribute."""
    entry = await _setup(hass, mock_client, "fr")
    registry = dr.async_get(hass)
    cellar = registry.async_get_device_by_identifier((DOMAIN, f"{SID}_sensor_4"), entry.entry_id)
    registry.async_update_device(cellar.id, name_by_user="Cave")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    groups = hass.states.get("alarm_control_panel.centrale_alarme_home").attributes["groups"]
    assert groups == {"2": ["Cave", "Détecteur 3"]}


async def test_a_refused_command_reads_in_the_server_language(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """The error raised when an automation is asked something it no longer lists is translated.

    Home Assistant skips an unavailable entity in a service call, so the entity is driven
    directly, as it would be in the moment between a read and the next state write.
    """
    await _setup(hass, mock_client, "en")
    platform = next(p for p in async_get_platforms(hass, DOMAIN) if p.domain == BUTTON_DOMAIN)
    gate = platform.entities["button.gate_g1"]
    with pytest.raises(HomeAssistantError) as err:
        await gate._send(None)
    assert err.value.translation_key == "command_not_available"
