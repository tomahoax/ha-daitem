"""Diagnostics download.

The point of these tests is the redaction: a diagnostics file is meant to be attached to a
public issue, so anything that would leak a credential is a security bug, not a cosmetic
one.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA
from custom_components.daitem.const import CONF_MASTER_CODE, CONF_SYSTEM_ID, DOMAIN
from custom_components.daitem.diagnostics import async_get_config_entry_diagnostics
from custom_components.daitem.redaction import redact
from custom_components.daitem.tokens import CONF_REFRESH_TOKEN


async def test_diagnostics_never_leak_the_secrets(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """The password, the alarm code and the refresh token must not appear anywhere."""
    hass.config_entries.async_update_entry(entry, data={**ENTRY_DATA, CONF_REFRESH_TOKEN: "the-refresh-token"})
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    dumped = json.dumps(diagnostics)

    for secret in (ENTRY_DATA[CONF_PASSWORD], ENTRY_DATA[CONF_MASTER_CODE], "the-refresh-token"):
        assert secret not in dumped
    # The email is kept only partially, enough to tell two accounts apart.
    assert ENTRY_DATA[CONF_EMAIL] not in dumped


async def test_diagnostics_carry_what_a_bug_report_needs(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["system_id"] == ENTRY_DATA[CONF_SYSTEM_ID]
    assert diagnostics["coordinator"]["last_update_success"] is True
    assert diagnostics["coordinator"]["arm_modes"] == ["away", "presence"]
    assert diagnostics["state"]["panel_state"] == "disarmed"
    assert diagnostics["state"]["session_busy"] is False
    # The raw payload is the only place an unmapped state shows up, so it must survive.
    assert diagnostics["raw"]["status"]["systemState"] == "off"


async def test_diagnostics_degrade_before_setup_finishes(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Diagnostics are most useful on an entry stuck retrying, where runtime_data is unset."""
    never_set_up = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="321")
    never_set_up.add_to_hass(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, never_set_up)

    assert diagnostics["coordinator"]["has_data"] is False
    assert "state" not in diagnostics


def test_redaction_catches_keys_nobody_anticipated() -> None:
    """A renamed field in a raw payload must be redacted on its name, not on a fixed list."""
    payload: dict[str, Any] = {
        "someNewAccessToken": "secret-value",
        "masterCode": "0000",
        "ttmSessionId": "abcdef123456",
        "nested": [{"userPassword": "hunter2"}],
        "serialNumber": "SN-0123456789",
        "systemState": "off",
        "session_busy": True,
    }

    redacted = redact(payload)

    assert redacted["someNewAccessToken"] == "***"
    assert redacted["masterCode"] == "***"
    assert redacted["ttmSessionId"] == "***"
    assert redacted["nested"][0]["userPassword"] == "***"
    # Identifiers stay correlatable, values that carry no identity stay intact.
    assert redacted["serialNumber"] == "SN-...789"
    assert redacted["systemState"] == "off"
    assert redacted["session_busy"] is True
