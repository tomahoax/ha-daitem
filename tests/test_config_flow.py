"""Config flow tests.

Covers the happy path and the error paths, a bronze-tier requirement of the Home
Assistant quality scale.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pydaitem import DaitemAuthError, DaitemError, System
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daitem.const import CONF_MASTER_CODE, CONF_SYSTEM_ID, DOMAIN

USER_INPUT = {
    CONF_EMAIL: "account@example.test",
    CONF_PASSWORD: "password",
    CONF_MASTER_CODE: "0000",
}


async def _start(hass: HomeAssistant) -> dict:
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_form_shown(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]


async def test_single_system_creates_entry(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home"
    assert result["data"][CONF_SYSTEM_ID] == 123456
    assert result["data"][CONF_EMAIL] == USER_INPUT[CONF_EMAIL]
    # The alarm code must be kept so later sessions can be opened.
    assert result["data"][CONF_MASTER_CODE] == USER_INPUT[CONF_MASTER_CODE]


async def test_invalid_auth(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    mock_client.login.side_effect = DaitemAuthError("invalid credentials")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cannot_connect(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    mock_client.login.side_effect = DaitemError("service unreachable")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_no_system(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    mock_client.account.list_systems.return_value = []
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_system"}


async def test_multiple_systems_prompts_choice(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    mock_client.account.list_systems.return_value = [
        System(id=1, name="Home", role=1),
        System(id=2, name="Office", role=0),
    ]
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "system"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_SYSTEM_ID: "2"})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SYSTEM_ID] == 2


async def test_unexpected_error_in_reauth_is_reported_as_unknown(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """An unexpected exception must not escape the flow, unlike the initial setup step.

    Regression: `async_step_reauth_confirm` had no `except Exception` safety net, unlike
    `async_step_user`, so a genuinely unexpected error would propagate into the flow
    machinery instead of being reported as "unknown".
    """
    mock_client.login.side_effect = RuntimeError("boom")
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home",
        data={
            CONF_EMAIL: "account@example.test",
            CONF_PASSWORD: "password",
            CONF_MASTER_CODE: "0000",
            CONF_SYSTEM_ID: 123456,
        },
        unique_id="123456",
    )
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password", CONF_MASTER_CODE: "9999"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_duplicate_system_aborts(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """The systemId is the unique id, so duplicates are impossible."""
    for expected in (FlowResultType.CREATE_ENTRY, FlowResultType.ABORT):
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        await hass.async_block_till_done()
        assert result["type"] is expected
