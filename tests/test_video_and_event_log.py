"""Cameras, the latest clip, and the event log.

Live video is out of reach (the app plays it through the camera vendor's SDK), so a camera
is a device with its status, and clips are summed up by the latest one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pydaitem import Camera, Clip, DaitemForbiddenError, Extras, LogEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA
from custom_components.daitem.const import DOMAIN
from custom_components.daitem.diagnostics import async_get_config_entry_diagnostics

CAMERA = Camera.from_json(
    {
        "id": 3,
        "uid": "cam-uid-123456",
        "type": "DAHUA",
        "name": "Entrée",
        "model": "IPC",
        "status": "ONLINE",
        "dahuaCloudInfo": {"playInfo": "vendor-secret", "channelId": "chan-secret"},
    }
)
OLD = Clip.from_json({"id": "f1", "timestamp": 1_600_000_000, "type": "ALARM", "category": "CAMERA"})
NEW = Clip.from_json(
    {"id": "f2", "timestamp": 1_700_000_000, "type": "ONDEMAND", "category": "DETECTOR", "durationMs": 8000}
)


async def setup(hass: HomeAssistant, mock_client: AsyncMock, extras: Extras, log: object = None) -> MockConfigEntry:
    mock_client.system.read_extras.return_value = extras
    if log is not None:
        if isinstance(log, Exception):
            mock_client.system.read_logbook.side_effect = log
        else:
            mock_client.system.read_logbook.return_value = log
    entry = MockConfigEntry(domain=DOMAIN, title="Home", data=ENTRY_DATA, unique_id="123456")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_a_camera_is_a_device_with_its_status(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await setup(hass, mock_client, Extras(automatisms=[], cameras=[CAMERA], clips=[]))
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, "123456_camera_3"), entry.entry_id)
    assert device is not None and device.name == "Entrée"
    assert hass.states.get("sensor.entree_camera_status").state == "ONLINE"


async def test_the_latest_clip_is_the_newest(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await setup(hass, mock_client, Extras(automatisms=[], cameras=[], clips=[OLD, NEW]))
    state = hass.states.get("sensor.alarm_panel_home_latest_clip")
    assert state is not None
    assert datetime.fromisoformat(state.state) == datetime.fromtimestamp(1_700_000_000, tz=UTC)
    assert state.attributes["kind"] == "ONDEMAND" and state.attributes["duration_s"] == 8.0
    assert state.attributes["clips"] == 2


async def test_no_video_hardware_no_clip_sensor(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await setup(hass, mock_client, Extras(automatisms=[], cameras=[], clips=[]))
    assert hass.states.get("sensor.alarm_panel_home_latest_clip") is None


LOG = [
    LogEntry.from_json({"date": "2026-09-07T15:22", "title": "logEvent.36.label2"}),
    LogEntry.from_json({"date": "2026-09-07T08:01", "title": "logEvent.1.label1"}),
]


async def test_event_log_entities_for_an_owner(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    await setup(hass, mock_client, Extras(automatisms=[], cameras=[], clips=[]), LOG)
    last = hass.states.get("sensor.alarm_panel_home_latest_event")
    assert last is not None and last.attributes["title"] == "logEvent.36.label2"
    # The history already there when Home Assistant starts is not replayed.
    assert hass.states.get("event.alarm_panel_home_event_log").state == "unknown"


async def test_a_new_entry_fires_an_event(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await setup(hass, mock_client, Extras(automatisms=[], cameras=[], clips=[]), LOG)
    newer = LogEntry.from_json(
        {"date": "2026-09-07T18:30", "title": "logEvent.9.label1", "details": [{"message": "m"}]}
    )
    mock_client.system.read_logbook.return_value = [newer, *LOG]
    await entry.runtime_data.event_log.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("event.alarm_panel_home_event_log")
    assert state.state != "unknown"
    assert state.attributes["event_type"] == "logged"
    assert state.attributes["title"] == "logEvent.9.label1"


async def test_a_restricted_account_gets_no_event_log(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = await setup(
        hass, mock_client, Extras(automatisms=[], cameras=[], clips=[]), DaitemForbiddenError("owner only")
    )
    assert entry.runtime_data.event_log is None
    assert hass.states.get("event.alarm_panel_home_event_log") is None
    assert hass.states.get("sensor.alarm_panel_home_latest_event") is None


async def test_diagnostics_carry_the_raw_answers_redacted(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    mock_client.system.collect_raw.return_value = {
        "system_id": 123456,
        "payloads": {"cameras": {"cameras": [CAMERA.raw]}, "automatisms": {"automatisms": []}},
        "errors": {"logbook": "DaitemForbiddenError: owner only"},
    }
    entry = await setup(hass, mock_client, Extras(automatisms=[], cameras=[CAMERA], clips=[NEW]))
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    dumped = json.dumps(diagnostics)
    assert diagnostics["raw_api"]["payloads"]["automatisms"] == {"automatisms": []}
    assert diagnostics["raw_api"]["errors"]["logbook"].startswith("DaitemForbiddenError")
    assert diagnostics["extras"]["cameras"] == [{"type": "DAHUA", "status": "ONLINE"}]
    for secret in ("vendor-secret", "chan-secret", "cam-uid-123456"):
        assert secret not in dumped
