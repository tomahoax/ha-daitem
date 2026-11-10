"""Shared fixtures for the Daitem integration tests.

No test touches a real alarm: the pydaitem library is always replaced by a double.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, create_autospec, patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pydaitem import (
    ArmMode,
    DaitemClient,
    DaitemError,
    DaitemSystem,
    Extras,
    Inventory,
    Snapshot,
    System,
    SystemStatus,
)
from pydaitem.client import ClientStats
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


#: Shapes taken from a live installation. Detector and control indices both start at 1 on
#: purpose: they really do collide, so anything keyed on the index alone breaks here.
INVENTORY_PAYLOAD = {
    "central": {
        "serialNumber": "SN-TEST",
        "type": "INTRUSION",
        "hasIO": True,
        "anomalies": {"defaultMediaAlert": False, "mainPowerSupplyAlert": False},
        "firmwareInfo": {
            "firmwares": [
                {"firmwareType": "SOFT", "currentVersion": {"releaseVersion": "6.4.13"}},
                {"firmwareType": "RADIO", "currentVersion": {"releaseVersion": "15"}},
            ]
        },
        "plug": {
            "serialNumber": "SN-PLUG",
            "firmwareInfo": {"firmwares": [{"firmwareType": "SOFT", "currentVersion": {"releaseVersion": "7.8.4"}}]},
        },
    },
    "genericSensors": {"sensors": []},
    "commands": [],
}


@pytest.fixture
def mock_inventory() -> Inventory:
    return Inventory.from_json(INVENTORY_PAYLOAD)


@pytest.fixture
def mock_client(mock_system: System, mock_status: SystemStatus, mock_inventory: Inventory) -> Generator[AsyncMock]:
    """Replace DaitemClient and the DaitemSystem façade with doubles.

    Tests drive the façade, mirroring what the integration actually talks to.
    """
    client = AsyncMock()
    client.login.return_value = None
    client.account.list_systems.return_value = [mock_system]

    # Shaped on a real DaitemSystem: a method the library renamed or removed fails here,
    # instead of answering whatever the test configured as a bare AsyncMock would.
    system = create_autospec(DaitemSystem(DaitemClient("a@example.test", "p"), mock_system.id, "0000"), instance=True)
    system.system_id = mock_system.id
    system.panel.read.return_value = mock_status
    system.inventory.read.return_value = mock_inventory
    system.panel.check_code.return_value = None
    # Real counters, empty, as a client that just started has: an autospec would answer mocks.
    system.client.stats = ClientStats()

    async def read_snapshot() -> Snapshot:
        """The library's own logic, over the two reads the tests configure."""
        snapshot = Snapshot()
        try:
            snapshot.inventory = await system.inventory.read()
        except DaitemError as err:
            snapshot.errors["inventory"] = err
        try:
            snapshot.status = await system.panel.read()
        except DaitemError as err:
            snapshot.errors["status"] = err
        return snapshot

    system.read_snapshot.side_effect = read_snapshot
    system.capabilities.arm_modes.return_value = frozenset({ArmMode.AWAY, ArmMode.PRESENCE})
    system.capabilities.discovered = True
    # Most installations have no automation, camera or clip: that is the default here.
    system.read_extras.return_value = Extras(automatisms=[], cameras=[], clips=[])
    system.logbook.read.return_value = []
    system.panel.transmitter_online.return_value = True
    system.collect_raw.return_value = {"system_id": mock_system.id, "payloads": {}, "errors": {}}

    with (
        patch("custom_components.daitem.config_flow.DaitemClient", return_value=client),
        patch("custom_components.daitem.DaitemClient", return_value=client) as client_cls,
        patch("custom_components.daitem.DaitemSystem", return_value=system),
        patch("custom_components.daitem.config_flow.DaitemSystem", return_value=system),
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
