"""Issues surfaced in Home Assistant's Repairs dashboard.

Two degradations that used to exist only as a log line nobody reads, while the user just
saw stale or missing features:

- the panel session held by another device for several cycles in a row, which freezes the
  state at its last known value;
- arming mode discovery blocked at setup, which silently leaves only away arming.

Neither has an automated fix (`is_fixable=False`): the panel has to become reachable
again, then the integration reloaded. What the Repairs entry adds is saying so.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

TROUBLESHOOTING_URL = "https://github.com/tomahoax/ha-daitem/blob/main/docs/troubleshooting.md"


def _session_busy_issue_id(system_id: int) -> str:
    return f"session_busy_{system_id}"


def _arm_modes_issue_id(system_id: int) -> str:
    return f"arm_modes_undiscovered_{system_id}"


@callback
def async_set_session_busy_issue(hass: HomeAssistant, system_id: int, *, active: bool) -> None:
    """Raise or clear the "another device holds the session" issue.

    Safe to call on every cycle: creating an existing issue de-dupes, deleting an absent
    one is a no-op.
    """
    issue_id = _session_busy_issue_id(system_id)
    if not active:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="session_busy",
        learn_more_url=TROUBLESHOOTING_URL,
    )


@callback
def async_set_arm_modes_issue(hass: HomeAssistant, system_id: int, *, active: bool) -> None:
    """Raise or clear the "only away arming is available" issue."""
    issue_id = _arm_modes_issue_id(system_id)
    if not active:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="arm_modes_undiscovered",
        learn_more_url=TROUBLESHOOTING_URL,
    )
