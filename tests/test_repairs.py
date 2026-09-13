"""Repairs entries for the two silent degradations.

Both used to be a log line only, so the user saw a frozen state or a missing arming mode
with nothing to explain it. What matters here is the threshold and the clearing: a single
409 is normal on this API and must stay invisible, and an issue that never goes away is
worse than no issue at all.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pydaitem import ArmMode, DaitemSessionBusyError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA
from custom_components.daitem.const import DOMAIN
from custom_components.daitem.coordinator import SESSION_BUSY_ISSUE_THRESHOLD

SESSION_BUSY_ISSUE = "session_busy_123456"
ARM_MODES_ISSUE = "arm_modes_undiscovered_123456"


async def test_occasional_session_busy_raises_nothing(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock, issue_registry: ir.IssueRegistry
) -> None:
    """Another device reading the panel once is routine, not something to report."""
    mock_client.system.read_status.side_effect = DaitemSessionBusyError("owner")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, SESSION_BUSY_ISSUE) is None


async def test_persistent_session_busy_is_reported_then_cleared(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock, issue_registry: ir.IssueRegistry
) -> None:
    """Held for several cycles in a row, the frozen state deserves an explanation."""
    coordinator = entry.runtime_data
    mock_client.system.read_status.side_effect = DaitemSessionBusyError("owner")
    for _ in range(SESSION_BUSY_ISSUE_THRESHOLD):
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    issue = issue_registry.async_get_issue(DOMAIN, SESSION_BUSY_ISSUE)
    assert issue is not None
    assert issue.translation_key == "session_busy"
    assert issue.is_fixable is False

    mock_client.system.read_status.side_effect = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, SESSION_BUSY_ISSUE) is None


async def test_blocked_arm_mode_discovery_is_reported(
    hass: HomeAssistant, mock_client: AsyncMock, issue_registry: ir.IssueRegistry
) -> None:
    """Presence arming silently missing from the entity must be visible somewhere."""
    mock_client.system.capabilities.discovered = False
    mock_client.system.capabilities.arm_modes.return_value = frozenset({ArmMode.AWAY})

    other = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="888")
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()

    issue = issue_registry.async_get_issue(DOMAIN, ARM_MODES_ISSUE)
    assert issue is not None
    assert issue.translation_key == "arm_modes_undiscovered"


async def test_arm_mode_issue_clears_once_discovery_succeeds(
    hass: HomeAssistant, mock_client: AsyncMock, issue_registry: ir.IssueRegistry
) -> None:
    """An issue that outlives the problem is worse than no issue at all."""
    mock_client.system.capabilities.discovered = False
    mock_client.system.capabilities.arm_modes.return_value = frozenset({ArmMode.AWAY})

    other = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="555")
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, ARM_MODES_ISSUE) is not None

    mock_client.system.capabilities.discovered = True
    mock_client.system.capabilities.arm_modes.return_value = frozenset({ArmMode.AWAY, ArmMode.PRESENCE})
    await other.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, ARM_MODES_ISSUE) is None


async def test_complete_arm_mode_discovery_reports_nothing(
    hass: HomeAssistant, entry: MockConfigEntry, issue_registry: ir.IssueRegistry
) -> None:
    assert issue_registry.async_get_issue(DOMAIN, ARM_MODES_ISSUE) is None
