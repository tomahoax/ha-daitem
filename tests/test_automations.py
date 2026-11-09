"""Automations: which entity each one becomes, and what pressing it sends.

The payloads follow pydaitem's models, which come from an analysis of the app's behaviour:
no real answer had been seen when this was written. What is pinned here is the mapping the
README documents (assumptions A1 and A2), so a correction after the first field report is
a deliberate change rather than an accident.
"""

from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.cover import ATTR_CURRENT_POSITION, ATTR_POSITION, CoverEntityFeature
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pydaitem import Automatism, DaitemError, DaitemSessionBusyError, Extras
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA
from custom_components.daitem.automatism import entity_kind
from custom_components.daitem.const import DOMAIN


def automatism(id_: str, label: str, category: str, commands: list[str], **state: object) -> Automatism:
    payload: dict[str, object] = {"id": id_, "label": label, "category": category, "availableCommands": commands}
    if state:
        payload["state"] = state
    return Automatism.from_json(payload)


GATE = automatism("g1", "Portail", "GATE", ["UP", "DOWN", "STOP"], state="OFF")
SHUTTER = automatism("s1", "Volet salon", "SHUTTER", ["UP", "DOWN", "STOP", "POSITION"], state="POSITION", position=40)
GARAGE = automatism("p1", "Garage", "GARAGE", ["PULSE"])
LIGHT = automatism("l1", "Terrasse", "LIGHT", ["ON", "OFF"], state="ON")
PLUG = automatism("o1", "Prise", "PLUG", ["ON", "OFF"], state="OFF")
ODD = automatism("x1", "Minuterie", "UNKNOW", ["TIMER"])


async def setup(hass: HomeAssistant, mock_client: AsyncMock, *automatisms: Automatism) -> MockConfigEntry:
    mock_client.system.read_extras.return_value = Extras(automatisms=list(automatisms), cameras=[], clips=[])
    entry = MockConfigEntry(domain=DOMAIN, title="Home", data=ENTRY_DATA, unique_id="123456")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize(
    ("item", "kind"),
    [(GATE, "cover"), (SHUTTER, "cover"), (GARAGE, "button"), (LIGHT, "light"), (PLUG, "switch"), (ODD, None)],
    ids=["gate", "shutter", "garage-impulse", "light", "plug", "timer-only"],
)
def test_each_automation_gets_the_entity_its_commands_allow(item: Automatism, kind: str | None) -> None:
    assert entity_kind(item) == kind


async def test_a_gate_is_a_cover_reading_closed_on_off(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await setup(hass, mock_client, GATE)
    state = hass.states.get("cover.portail")
    assert state is not None
    assert state.state == "closed"
    assert state.attributes[ATTR_DEVICE_CLASS] == "gate"
    assert state.attributes[ATTR_ASSUMED_STATE] is True
    features = CoverEntityFeature(state.attributes[ATTR_SUPPORTED_FEATURES])
    assert features == CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP


async def test_opening_sends_up_and_reads_again(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await setup(hass, mock_client, GATE)
    await hass.services.async_call(COVER_DOMAIN, SERVICE_OPEN_COVER, {ATTR_ENTITY_ID: "cover.portail"}, blocking=True)
    mock_client.system.automation.command.assert_awaited_once_with(GATE, "UP", position=None)
    # Two follow-up reads are scheduled, the command answer carrying no state.
    assert len(entry.runtime_data._follow_ups) == 2


async def test_a_shutter_reports_and_takes_a_position(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await setup(hass, mock_client, SHUTTER)
    state = hass.states.get("cover.volet_salon")
    assert state is not None
    assert state.state == "open"
    assert state.attributes[ATTR_CURRENT_POSITION] == 40
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {ATTR_ENTITY_ID: "cover.volet_salon", ATTR_POSITION: 70},
        blocking=True,
    )
    mock_client.system.automation.command.assert_awaited_once_with(SHUTTER, "POSITION", position=70)


async def test_closing_falls_back_to_position_zero(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    only_position = automatism("s2", "Store", "SHUTTER", ["POSITION"], state="POSITION", position=100)
    await setup(hass, mock_client, only_position)
    await hass.services.async_call(COVER_DOMAIN, SERVICE_CLOSE_COVER, {ATTR_ENTITY_ID: "cover.store"}, blocking=True)
    mock_client.system.automation.command.assert_awaited_once_with(only_position, "POSITION", position=0)


async def test_an_impulse_only_garage_is_a_button(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await setup(hass, mock_client, GARAGE)
    assert hass.states.get("cover.garage") is None
    await hass.services.async_call(BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: "button.garage"}, blocking=True)
    mock_client.system.automation.command.assert_awaited_once_with(GARAGE, "PULSE", position=None)


async def test_lights_and_plugs(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await setup(hass, mock_client, LIGHT, PLUG)
    assert hass.states.get("light.terrasse").state == "on"
    plug = hass.states.get("switch.prise")
    assert plug.state == "off" and plug.attributes[ATTR_DEVICE_CLASS] == "outlet"
    await hass.services.async_call(LIGHT_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: "light.terrasse"}, blocking=True)
    await hass.services.async_call(SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: "switch.prise"}, blocking=True)
    calls = [c.args[:2] for c in mock_client.system.automation.command.await_args_list]
    assert calls == [(LIGHT, "OFF"), (PLUG, "ON")]


async def test_each_automation_is_its_own_device(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await setup(hass, mock_client, GATE)
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, "123456_automatism_g1"), entry.entry_id)
    assert device is not None
    assert device.name == "Portail" and device.model == "GATE"
    assert device.via_device_id == entry.runtime_data.panel_device_id


async def test_an_automation_nothing_fits_is_logged(
    hass: HomeAssistant, mock_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        await setup(hass, mock_client, ODD)
    assert "Minuterie" in caplog.text and "TIMER" in caplog.text


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (DaitemSessionBusyError("owner"), "another device"),
        (DaitemError("refused"), "Daitem command rejected"),
    ],
)
async def test_a_failed_command_says_why(
    hass: HomeAssistant, mock_client: AsyncMock, error: Exception, message: str
) -> None:
    await setup(hass, mock_client, GATE)
    mock_client.system.automation.command.side_effect = error
    with pytest.raises(HomeAssistantError, match=message):
        await hass.services.async_call(
            COVER_DOMAIN, SERVICE_OPEN_COVER, {ATTR_ENTITY_ID: "cover.portail"}, blocking=True
        )


async def test_a_failed_read_keeps_the_automations(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await setup(hass, mock_client, GATE)
    coordinator = entry.runtime_data
    mock_client.system.read_extras.return_value = Extras(
        automatisms=None, cameras=[], clips=[], errors={"automatisms": DaitemError("down")}
    )
    coordinator._extras_due = 0.0
    await coordinator.async_refresh()
    assert coordinator.data.automatisms == [GATE]
    assert hass.states.get("cover.portail").state == "closed"


async def test_installations_without_automations_are_read_rarely(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await setup(hass, mock_client)
    assert entry.runtime_data._extras_due - time.monotonic() > 1700
    mock_client.system.read_extras.reset_mock()
    await entry.runtime_data.async_refresh()
    mock_client.system.read_extras.assert_not_awaited()
