"""The integration with the real library, against pydaitem's own fake Daitem service.

`pydaitem.testing.FakeDaitem` serves the sign-in, the panel and its commands with the levers
of each edge case: the mobile app holding the panel, a wrong code, the transmitter offline,
any server message. It ships with the library, so it follows the API as the library sees
it, and this file needs no answer of its own. The automations, cameras, clips and the event
log are not served there: `test_end_to_end.py` keeps its own server for those.
"""

from __future__ import annotations

import functools
from collections.abc import AsyncIterator
from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.components.alarm_control_panel import DOMAIN as ALARM_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_ALARM_ARM_AWAY, SERVICE_ALARM_DISARM
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pydaitem import DaitemClient, ServerMessage
from pydaitem.testing import FakeDaitem
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA
from custom_components.daitem.const import CONF_MASTER_CODE, DOMAIN

ALARM = "alarm_control_panel.alarm_panel_home"
CONNECTIVITY = "binary_sensor.alarm_panel_home_transmitter"


@pytest.fixture
async def fake(socket_enabled: None, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeDaitem]:
    """The fake service, with the account and the code of the test entry."""
    async with FakeDaitem(
        email=ENTRY_DATA["email"],
        password=ENTRY_DATA["password"],
        code=ENTRY_DATA[CONF_MASTER_CODE],
        system_id=ENTRY_DATA["system_id"],
    ) as service:
        client = functools.partial(DaitemClient, api_base=service.url, auth_base=service.url)
        monkeypatch.setattr("custom_components.daitem.DaitemClient", client)
        monkeypatch.setattr("custom_components.daitem.config_flow.DaitemClient", client)
        yield service


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Home", data=ENTRY_DATA, unique_id=str(ENTRY_DATA["system_id"]))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _configure(hass: HomeAssistant, **overrides: Any) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    user_input = {key: ENTRY_DATA[key] for key in ("email", "password", CONF_MASTER_CODE)}
    return await hass.config_entries.flow.async_configure(result["flow_id"], {**user_input, **overrides})


async def test_setup_checks_the_code_on_the_panel(hass: HomeAssistant, fake: FakeDaitem) -> None:
    result = await _configure(hass)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert not fake.session_open


async def test_setup_refuses_a_wrong_code(hass: HomeAssistant, fake: FakeDaitem) -> None:
    result = await _configure(hass, **{CONF_MASTER_CODE: "9999"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_code"}


async def test_setup_says_the_panel_is_busy_rather_than_the_code_wrong(hass: HomeAssistant, fake: FakeDaitem) -> None:
    fake.held_by = "Phone"
    result = await _configure(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "panel_busy"}


async def test_arming_publishes_the_state_and_frees_the_panel(hass: HomeAssistant, fake: FakeDaitem) -> None:
    entry = await _setup(hass)
    assert hass.states.get(ALARM).state == "disarmed"

    await hass.services.async_call(ALARM_DOMAIN, SERVICE_ALARM_ARM_AWAY, {ATTR_ENTITY_ID: ALARM}, blocking=True)
    assert hass.states.get(ALARM).state == "armed_away"
    # The library releases the panel in the background once the command has answered.
    await entry.runtime_data.system.client.panel.wait_released()
    assert not fake.session_open

    await hass.services.async_call(ALARM_DOMAIN, SERVICE_ALARM_DISARM, {ATTR_ENTITY_ID: ALARM}, blocking=True)
    assert hass.states.get(ALARM).state == "disarmed"


async def test_the_mobile_app_holding_the_panel_keeps_the_state(hass: HomeAssistant, fake: FakeDaitem) -> None:
    entry = await _setup(hass)
    fake.held_by = "Phone"
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ALARM).state == "disarmed"


async def test_a_rate_limit_keeps_the_state(hass: HomeAssistant, fake: FakeDaitem) -> None:
    entry = await _setup(hass)
    fake.fail("POST", "/connect", status=403, message=ServerMessage.OVER_LIMIT)
    refused_before = entry.runtime_data.system.client.stats.refused_locally
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert entry.runtime_data.last_update_success is True
    # The library is pausing: the next call is refused without reaching Daitem.
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.system.client.stats.refused_locally > refused_before
    assert entry.runtime_data.last_update_success is True
    assert hass.states.get(ALARM).state == "disarmed"


async def test_an_offline_transmitter_is_told_apart_from_an_outage(hass: HomeAssistant, fake: FakeDaitem) -> None:
    entry = await _setup(hass)
    assert hass.states.get(CONNECTIVITY).state == "on"

    fake.online = False
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await coordinator.connectivity.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(ALARM).state == "unavailable"
    assert hass.states.get(CONNECTIVITY).state == "off"
