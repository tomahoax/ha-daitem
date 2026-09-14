"""Coordinator tests, in particular graceful degradation.

The most important invariant of this integration: when another device holds the panel
session, the alarm must not become unavailable in Home Assistant.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.alarm_control_panel import AlarmControlPanelEntityFeature
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pydaitem import (
    ArmMode,
    DaitemError,
    DaitemForbiddenError,
    DaitemSessionBusyError,
    Inventory,
    SystemStatus,
    TokenStore,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA
from custom_components.daitem.const import (
    ARMING_SCAN_INTERVAL,
    CONF_MASTER_CODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.daitem.tokens import CONF_REFRESH_TOKEN, ConfigEntryTokenStore


async def test_setup_creates_alarm_entity(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    state = hass.states.get("alarm_control_panel.alarm_home")
    assert state is not None
    assert state.state == "disarmed"


async def test_panel_device_name_is_localized(
    hass: HomeAssistant, entry: MockConfigEntry, device_registry: dr.DeviceRegistry
) -> None:
    """The panel must stand out from the plain detector devices in the device list.

    Named "Alarm - {installation name}" (translated), rather than just the installation
    name, so it is not mistaken for one more device among the fault sensors.
    """
    device = device_registry.async_get_device_by_identifier((DOMAIN, "123456"), entry.entry_id)
    assert device is not None
    assert device.name == "Alarm - Home"


async def test_fault_sensor_names_come_from_the_translations(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Fault sensors are named by translation key, which is also what gives them an icon.

    Worth proving rather than deducing: resolution depends on Home Assistant loading the
    platform translations asynchronously, and a key missing from `strings.json` produces a
    nameless entity rather than an error.
    """
    state = hass.states.get("binary_sensor.alarm_home_main_power_supply")
    assert state is not None
    assert state.attributes["friendly_name"] == "Alarm - Home Main power supply"


async def test_session_busy_keeps_last_known_state(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A 409 must not make the entity unavailable."""
    coordinator = entry.runtime_data
    assert coordinator.data.status.state == "off"

    mock_client.system.read_status.side_effect = DaitemSessionBusyError("owner")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is True
    assert coordinator.data.status.state == "off"
    assert coordinator.data.session_busy is True

    state = hass.states.get("alarm_control_panel.alarm_home")
    assert state is not None
    assert state.state != "unavailable"


async def test_forbidden_on_connect_starts_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A wrong master code is a 403 on connect, not a generic error to retry forever.

    Regression: it used to fall through to a plain UpdateFailed, leaving the user stuck
    in "Failed setup, will retry" with no way to correct the code from the UI.
    """
    mock_client.system.read_status.side_effect = DaitemForbiddenError(
        "GET /systems/123456/state: access denied for this account"
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(flow["context"].get("source") == "reauth" for flow in flows)


async def test_polling_speeds_up_while_arming(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """While the delay runs the interval tightens, then returns to normal."""
    coordinator = entry.runtime_data
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)

    mock_client.system.read_status.return_value = SystemStatus.from_json({"systemState": "tempo", "groups": []})
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(seconds=ARMING_SCAN_INTERVAL)

    mock_client.system.read_status.return_value = SystemStatus.from_json({"systemState": "on", "groups": []})
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)


async def test_away_only_after_blocked_discovery_warns(
    hass: HomeAssistant, mock_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Presence/night silently vanishing from the panel entity must not go unnoticed.

    Regression: this degradation used to be completely silent, because the coordinator's
    own `except DaitemError` never actually fires - pydaitem's façade swallows discovery
    failures itself and returns away alone.
    """
    mock_client.system.capabilities.discovered = False
    mock_client.system.capabilities.arm_modes.return_value = frozenset({ArmMode.AWAY})

    other = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="777")
    other.add_to_hass(hass)
    with caplog.at_level(logging.WARNING, logger="custom_components.daitem.coordinator"):
        assert await hass.config_entries.async_setup(other.entry_id)
        await hass.async_block_till_done()

    assert "only away arming will be offered" in caplog.text
    assert "retried on the next cycles" in caplog.text


async def test_blocked_discovery_recovers_without_a_reload(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """The Home button must come back on its own once the panel is free again.

    Regression: discovery ran once at setup and `supported_features` was frozen in the
    entity constructor, so a panel busy for the one second setup took left the
    installation on away-only arming until somebody reloaded the integration by hand.
    """
    mock_client.system.capabilities.discovered = False
    mock_client.system.capabilities.arm_modes.return_value = frozenset({ArmMode.AWAY})

    other = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="999")
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()

    features = hass.states.get("alarm_control_panel.alarm_annexe").attributes["supported_features"]
    assert not features & AlarmControlPanelEntityFeature.ARM_HOME

    mock_client.system.capabilities.discovered = True
    mock_client.system.capabilities.arm_modes.return_value = frozenset({ArmMode.AWAY, ArmMode.PRESENCE})
    await other.runtime_data.async_refresh()
    await hass.async_block_till_done()

    features = hass.states.get("alarm_control_panel.alarm_annexe").attributes["supported_features"]
    assert features & AlarmControlPanelEntityFeature.ARM_HOME


async def test_discovery_is_not_retried_once_it_has_succeeded(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A retry on every cycle would be a pointless extra call on a working installation."""
    calls_after_setup = mock_client.system.capabilities.arm_modes.await_count

    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert mock_client.system.capabilities.arm_modes.await_count == calls_after_setup


async def test_genuine_away_only_installation_does_not_warn(
    hass: HomeAssistant, mock_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """An installation that genuinely defines no partial preset must not look degraded."""
    mock_client.system.capabilities.discovered = True
    mock_client.system.capabilities.arm_modes.return_value = frozenset({ArmMode.AWAY})

    other = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="666")
    other.add_to_hass(hass)
    with caplog.at_level(logging.WARNING, logger="custom_components.daitem.coordinator"):
        assert await hass.config_entries.async_setup(other.entry_id)
        await hass.async_block_till_done()

    assert "only away arming will be offered" not in caplog.text


async def test_unmapped_partial_states_show_as_unknown_not_guessed(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A named preset's own armed state is not shown as Night/Vacation: it is a guess.

    `tempo1` (an exit delay in progress) stays a generic "arming", which asserts nothing
    about which mode. Once armed via a preset (`partial1`), pydaitem cannot verify what
    that preset actually means beyond "presence", so the entity honestly shows unknown
    rather than assuming it means "night".
    """
    mock_client.system.read_status.return_value = SystemStatus.from_json({"systemState": "tempo1", "groups": []})
    await entry.runtime_data.async_refresh()
    assert hass.states.get("alarm_control_panel.alarm_home").state == "arming"

    mock_client.system.read_status.return_value = SystemStatus.from_json({"systemState": "partial1", "groups": []})
    await entry.runtime_data.async_refresh()
    assert hass.states.get("alarm_control_panel.alarm_home").state == "unknown"


async def test_night_and_vacation_are_never_advertised(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Guessed labels must never be offered, however many presets are discovered.

    Only Away and Presence (Home) have a verified meaning: Away is the base command,
    Presence is confirmed by its technical key. A named preset beyond that cannot be
    trusted to mean "night" or "vacation", so there is no way to enable it from Home
    Assistant at all.
    """
    mock_client.system.capabilities.arm_modes.return_value = frozenset(
        {ArmMode.AWAY, ArmMode.PRESENCE, ArmMode.PARTIAL, ArmMode.PARTIAL_2}
    )

    other = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="444")
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("alarm_control_panel.alarm_annexe")
    assert state is not None
    features = state.attributes["supported_features"]
    assert not features & AlarmControlPanelEntityFeature.ARM_NIGHT
    assert not features & AlarmControlPanelEntityFeature.ARM_VACATION
    assert features & AlarmControlPanelEntityFeature.ARM_AWAY
    assert features & AlarmControlPanelEntityFeature.ARM_HOME


async def test_unload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is not None


async def test_faults_follow_the_inventory(hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock) -> None:
    """A fault appearing after startup must reach the entity.

    Regression: the inventory used to be fetched once, so faults were frozen at startup
    and a flat battery or an opened tamper would never have surfaced.
    """
    power = "binary_sensor.alarm_home_main_power_supply"
    assert hass.states.get(power).state == "off"

    mock_client.system.read_inventory.return_value = Inventory.from_json(
        {
            "central": {
                "serialNumber": "SN-TEST",
                "type": "INTRUSION",
                "anomalies": {"mainPowerSupplyAlert": True, "defaultMediaAlert": False},
            },
            "genericSensors": {"sensors": []},
            "commands": [],
        }
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(power).state == "on"


async def test_detector_faults_become_their_own_device(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Each detector reporting an anomaly gets its own device, not just the panel's."""
    mock_client.system.read_inventory.return_value = Inventory.from_json(
        {
            "central": {"serialNumber": "SN-CENTRAL", "type": "INTRUSION", "anomalies": {}},
            "genericSensors": {
                "sensors": [
                    {
                        "index": 1,
                        "name": "Front door",
                        "serialNumber": "SN-1",
                        "type": "DEFAULT",
                        "anomalies": {"powerSupplyAlert": True, "radioAlert": False},
                    }
                ]
            },
            "commands": [],
        }
    )
    other = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="888")
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()

    battery = hass.states.get("binary_sensor.front_door_battery")
    assert battery is not None
    assert battery.state == "on"

    radio = hass.states.get("binary_sensor.front_door_radio")
    assert radio is not None
    assert radio.state == "off"

    # Masking is not among the anomaly keys this device reports, so no entity for it.
    assert hass.states.get("binary_sensor.front_door_masking") is None


async def test_secondary_detector_faults_are_created_but_hidden(
    hass: HomeAssistant, mock_client: AsyncMock, entity_registry: er.EntityRegistry
) -> None:
    """Only battery and radio clutter the entity list; the rest stay available but hidden."""
    mock_client.system.read_inventory.return_value = Inventory.from_json(
        {
            "central": {"serialNumber": "SN-CENTRAL", "type": "INTRUSION", "anomalies": {}},
            "genericSensors": {
                "sensors": [
                    {
                        "index": 1,
                        "name": "Garden",
                        "serialNumber": "SN-2",
                        "type": "DEFAULT",
                        "anomalies": {
                            "powerSupplyAlert": False,
                            "radioAlert": False,
                            "maskAlert": False,
                        },
                    }
                ]
            },
            "commands": [],
        }
    )
    other = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="777")
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()

    # Hidden must not mean absent: state, history and automations still work.
    assert hass.states.get("binary_sensor.garden_masking") is not None
    assert entity_registry.async_get("binary_sensor.garden_masking").hidden_by is er.RegistryEntryHider.INTEGRATION
    # A future edit hiding battery/radio too must fail this.
    assert entity_registry.async_get("binary_sensor.garden_battery").hidden_by is None
    assert entity_registry.async_get("binary_sensor.garden_radio").hidden_by is None


async def test_reinstall_does_not_leave_hidden_faults_visible(
    hass: HomeAssistant, mock_client: AsyncMock, entity_registry: er.EntityRegistry
) -> None:
    """A fault sensor restored visible by Home Assistant's own registry gets corrected.

    Regression: removing and re-adding the integration with the same account does not
    erase entities from the registry. Home Assistant keeps a `deleted_entities` record
    and replays its old `hidden_by` on re-registration instead of applying the current
    default, so a fault sensor created before this default existed - or removed and
    re-added since - came back visible. Simulated here by pre-creating the entity, since
    reproducing the real removal flow needs the row to survive it, which the test setup
    below does not exercise.
    """
    mock_client.system.read_inventory.return_value = Inventory.from_json(
        {
            "central": {"serialNumber": "SN-CENTRAL", "type": "INTRUSION", "anomalies": {}},
            "genericSensors": {
                "sensors": [
                    {
                        "index": 1,
                        "name": "Garden",
                        "serialNumber": "SN-2",
                        "type": "DEFAULT",
                        "anomalies": {"maskAlert": False},
                    }
                ]
            },
            "commands": [],
        }
    )
    entry = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="555")
    entry.add_to_hass(hass)

    unique_id = "123456_sensor_1_masking"
    pre_existing = entity_registry.async_get_or_create("binary_sensor", DOMAIN, unique_id, config_entry=entry)
    assert pre_existing.hidden_by is None

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = entity_registry.async_get_entity_id("binary_sensor", DOMAIN, unique_id)
    assert entity_registry.async_get(entity_id).hidden_by is er.RegistryEntryHider.INTEGRATION

    # The correction is one-off: a visibility choice made afterwards must survive a reload.
    entity_registry.async_update_entity(entity_id, hidden_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert entity_registry.async_get(entity_id).hidden_by is None


async def test_entities_exist_even_if_the_inventory_fails(
    hass: HomeAssistant, mock_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing inventory must not permanently deprive the user of fault entities."""
    mock_client.system.read_inventory.side_effect = DaitemError("inventory unavailable")
    other = MockConfigEntry(domain=DOMAIN, title="Annexe", data=ENTRY_DATA, unique_id="999")
    other.add_to_hass(hass)
    with caplog.at_level(logging.WARNING):
        assert await hass.config_entries.async_setup(other.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.alarm_annexe_main_power_supply")
    assert state is not None
    # Unknown, not missing: the entity exists and will populate once the inventory returns.
    assert state.state == "unknown"

    # The permanent loss of the per-detector entities must be visible, not just the
    # central sensors falling back silently.
    assert "no per-detector fault sensor could be created" in caplog.text


async def test_refresh_token_is_persisted_in_the_config_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Home Assistant must resume its session across restarts, not re-run the login form."""
    store = ConfigEntryTokenStore(hass, entry)
    assert await store.load() is None

    await store.save("stored-refresh-token")
    await hass.async_block_till_done()
    assert entry.data[CONF_REFRESH_TOKEN] == "stored-refresh-token"
    assert await store.load() == "stored-refresh-token"

    # Saving the same value again must not rewrite the entry.
    before = entry.data
    await store.save("stored-refresh-token")
    assert entry.data is before

    await store.save(None)
    await hass.async_block_till_done()
    assert CONF_REFRESH_TOKEN not in entry.data


async def test_client_is_built_with_a_token_store(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Guards the production wiring that the mocks would otherwise hide.

    The client is an AsyncMock, so it accepts any keyword silently. Without this
    assertion a renamed argument, or a store no longer satisfying the protocol, would
    pass CI and break at runtime for every user.
    """
    store = mock_client.constructor.call_args.kwargs["token_store"]
    assert isinstance(store, TokenStore)


async def test_reauth_drops_the_stored_refresh_token(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    """Re-authenticating must not resume the session the user meant to cut off.

    Someone re-authenticates because they changed their Daitem password. Keycloak does
    not necessarily revoke the old refresh token, so keeping it would defeat the point.
    """
    stale = {**ENTRY_DATA, CONF_REFRESH_TOKEN: "token-from-the-old-password"}
    config_entry = MockConfigEntry(domain=DOMAIN, title="Home", data=stale, unique_id="123456")
    config_entry.add_to_hass(hass)

    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password", CONF_MASTER_CODE: "9999"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert CONF_REFRESH_TOKEN not in config_entry.data
    assert config_entry.data[CONF_PASSWORD] == "new-password"


async def test_token_store_survives_a_removed_entry(
    hass: HomeAssistant, entry: MockConfigEntry, caplog: pytest.LogCaptureFixture
) -> None:
    """A poll finishing after the integration was removed must not raise."""
    store = ConfigEntryTokenStore(hass, entry)
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    # Must not raise: rotating a token we can no longer store is harmless.
    with caplog.at_level(logging.DEBUG, logger="custom_components.daitem.tokens"):
        await store.save("token-arriving-too-late")

    # The cause must be traceable even though it is silently tolerated.
    assert "Config entry gone, refresh token not persisted:" in caplog.text
