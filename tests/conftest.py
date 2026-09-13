"""Shared fixtures for the Daitem integration tests.

No test touches a real alarm: the pydaitem library is always replaced by a double.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pydaitem import ArmMode, Inventory, System, SystemStatus
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daitem.const import CONF_MASTER_CODE, CONF_SYSTEM_ID, DOMAIN

pytest_plugins = ["pytest_homeassistant_custom_component"]

ENTRY_DATA = {
    CONF_EMAIL: "account@example.test",
    CONF_PASSWORD: "password",
    CONF_MASTER_CODE: "0000",
    CONF_SYSTEM_ID: 123456,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make the custom integration loadable in tests."""
    return


@pytest.fixture
def mock_system() -> System:
    return System(id=123456, name="Home", role=0, vendor="edaitem")


@pytest.fixture
def mock_status() -> SystemStatus:
    return SystemStatus.from_json(
        {
            "systemState": "off",
            "groups": [{"id": 1, "active": False}, {"id": 2, "active": False}],
            "commandStatus": "CMD_OK",
        }
    )


@pytest.fixture
def mock_inventory() -> Inventory:
    return Inventory.from_json(
        {
            "central": {
                "serialNumber": "SN-TEST",
                "type": "INTRUSION",
                "hasIO": True,
                "anomalies": {"defaultMediaAlert": False, "mainPowerSupplyAlert": False},
                "plug": {"serialNumber": "SN-PLUG"},
            },
            "genericSensors": {"sensors": []},
            "commands": [],
        }
    )


@pytest.fixture
def mock_client(mock_system: System, mock_status: SystemStatus, mock_inventory: Inventory) -> Generator[AsyncMock]:
    """Replace DaitemClient and the DaitemSystem façade with doubles.

    Tests drive the façade, mirroring what the integration actually talks to.
    """
    client = AsyncMock()
    client.login.return_value = None
    client.account.list_systems.return_value = [mock_system]

    system = AsyncMock()
    system.system_id = mock_system.id
    system.read_status.return_value = mock_status
    system.read_inventory.return_value = mock_inventory
    system.capabilities.arm_modes.return_value = frozenset({ArmMode.AWAY, ArmMode.PRESENCE})
    system.capabilities.discovered = True

    with (
        patch("custom_components.daitem.config_flow.DaitemClient", return_value=client),
        patch("custom_components.daitem.DaitemClient", return_value=client) as client_cls,
        patch("custom_components.daitem.DaitemSystem", return_value=system),
    ):
        client.system = system
        # Exposed so tests can assert how the integration builds the client. Without it
        # an AsyncMock swallows every keyword, and a renamed argument would ship green.
        client.constructor = client_cls
        yield client


@pytest.fixture
async def entry(hass: HomeAssistant, mock_client: AsyncMock) -> MockConfigEntry:
    """A configured installation, set up and ready."""
    config_entry = MockConfigEntry(domain=DOMAIN, title="Home", data=ENTRY_DATA, unique_id="123456")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
