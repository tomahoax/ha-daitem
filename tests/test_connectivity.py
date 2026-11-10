"""The transmitter's connectivity, read apart from the panel.

What it is for: when the alarm turns unavailable, telling an offline box from a Daitem
outage. So it has to keep answering while the panel cannot be read.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pydaitem import DaitemError, DaitemForbiddenError, DaitemTransmitterOfflineError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA
from custom_components.daitem.const import DOMAIN
from custom_components.daitem.diagnostics import async_get_config_entry_diagnostics

ENTITY = "binary_sensor.alarm_panel_home_transmitter"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Home", data=ENTRY_DATA, unique_id="123456")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_an_online_transmitter_reads_connected(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await _setup(hass)
    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state == "on"
    assert state.attributes["device_class"] == "connectivity"


async def test_it_still_answers_while_the_panel_cannot_be_read(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """The alarm turns unavailable, the connectivity sensor says why."""
    entry = await _setup(hass)
    coordinator = entry.runtime_data
    mock_client.system.panel.read.side_effect = DaitemTransmitterOfflineError("transmitter.connection.failed")
    mock_client.system.panel.transmitter_online.return_value = False

    await coordinator.async_refresh()
    await coordinator.connectivity.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("alarm_control_panel.alarm_panel_home").state == "unavailable"
    assert hass.states.get(ENTITY).state == "off"


async def test_a_failed_read_makes_it_unavailable(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await _setup(hass)
    mock_client.system.panel.transmitter_online.side_effect = DaitemError("down")
    await entry.runtime_data.connectivity.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == "unavailable"


async def test_an_account_refused_the_read_gets_no_sensor(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    mock_client.system.panel.transmitter_online.side_effect = DaitemForbiddenError("owner only")
    entry = await _setup(hass)
    assert entry.runtime_data.connectivity is None
    assert hass.states.get(ENTITY) is None


async def test_diagnostics_say_whether_it_is_online(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await _setup(hass)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["extras"]["transmitter_connectivity"] == {
        "enabled": True,
        "last_update_success": True,
        "online": True,
    }
