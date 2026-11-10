"""The integration with the real pydaitem library, against a fake Topaze on localhost.

The other tests replace the library with a double. This one does not: the façade, the
transport, the job polling and the models all run, so a mismatch between what the
integration expects and what the library returns fails here. The answers follow the
library's models: when the API is found to answer otherwise, this server is the place to
correct them.
"""

from __future__ import annotations

import functools
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from pydaitem import DaitemClient
from pydaitem.client import logbook
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import ENTRY_DATA
from custom_components.daitem.const import DOMAIN
from custom_components.daitem.diagnostics import async_get_config_entry_diagnostics
from custom_components.daitem.tokens import CONF_REFRESH_TOKEN

SID = ENTRY_DATA["system_id"]
BASE = f"/topaze/v5/systems/{SID}"


def reply(body: Any, **kwargs: Any) -> Callable[[web.Request], Awaitable[web.Response]]:
    async def handler(_request: web.Request) -> web.Response:
        return web.json_response(body, **kwargs)

    return handler


class FakeTopaze:
    """Just enough of the API for one installation with a gate, a camera and a clip."""

    def __init__(self) -> None:
        self.commands: list[dict[str, Any]] = []

    def routes(self) -> list[web.RouteDef]:
        return [
            web.post(
                "/realms/daitem/protocol/openid-connect/token",
                reply({"access_token": "at", "refresh_token": "rt", "expires_in": 1800}),
            ),
            web.get(f"{BASE}/state", reply({"systemState": "off", "groups": []})),
            web.post(f"{BASE}/connect", reply({"ttmSessionId": "s", "systemState": "off"})),
            web.post(f"{BASE}/disconnect", reply({"status": "OK"})),
            web.get("/topaze/v1/user", reply({"userId": 42})),
            web.get(f"/topaze/v1/widgets/systems/{SID}/users/42", reply({"widgets": []})),
            web.get(
                f"/topaze/v2/systems/{SID}/configuration",
                reply({"central": {"serialNumber": "SN-CENTRAL", "type": "INTRUSION"}}),
            ),
            web.get(
                f"{BASE}/automatisms",
                reply(
                    {
                        "automatisms": [
                            {"id": "g1", "label": "Portail", "category": "GATE", "availableCommands": ["PULSE"]},
                        ]
                    }
                ),
            ),
            web.post(f"{BASE}/automatisms/g1/command", self.command),
            web.get(
                f"/topaze/v1/systems/{SID}/cameras",
                reply(
                    {
                        "cameras": [
                            {
                                "id": 3,
                                "uid": "cam-uid-123456",
                                "type": "DAHUA",
                                "name": "Entrée",
                                "model": "IPC",
                                "status": "ONLINE",
                                "dahuaInfo": {"index": 0, "deeplink": "vendor-secret"},
                            },
                        ]
                    }
                ),
            ),
            web.get(
                f"/topaze/v6/systems/{SID}/videos",
                reply(
                    {
                        "videos": [
                            {"id": "f1", "timestamp": 1_700_000_000_000, "type": "ALARM", "category": "CAMERA"},
                        ]
                    }
                ),
            ),
            web.get(f"/topaze/v6/systems/{SID}/scenarios", reply({"scenarios": []})),
            web.get(f"{BASE}/schedule", reply({"programs": []})),
            web.post("/topaze/configuration/getConfiguration", reply({"transmitterId": "tx-1"})),
            web.post("/topaze/installation/isConnected", reply({"isConnected": True})),
            web.post(
                f"{BASE}/logbook",
                reply({"message": "ACCEPTED"}, status=202, headers={"Location": f"/v5/systems/{SID}/logbook/j1"}),
            ),
            web.get(
                f"{BASE}/logbook/j1",
                reply(
                    {
                        "status": "request_status_done",
                        "response": [
                            {"date": "2026-09-07T15:22", "title": "logEvent.36.label2", "details": []},
                        ],
                    }
                ),
            ),
        ]

    async def command(self, request: web.Request) -> web.Response:
        self.commands.append(await request.json())
        return web.json_response({})


@pytest.fixture
async def topaze(socket_enabled: None) -> AsyncIterator[tuple[FakeTopaze, str]]:
    fake = FakeTopaze()
    app = web.Application()
    app.add_routes(fake.routes())
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        yield fake, str(server.make_url("")).rstrip("/")
    finally:
        await server.close()


async def test_the_real_library_feeds_every_new_entity(
    hass: HomeAssistant, topaze: tuple[FakeTopaze, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, base = topaze
    monkeypatch.setattr(logbook, "LOGBOOK_POLL_INTERVAL", 0.0)
    monkeypatch.setattr(
        "custom_components.daitem.DaitemClient",
        functools.partial(DaitemClient, api_base=base, auth_base=base),
    )
    entry = MockConfigEntry(
        domain=DOMAIN, title="Home", data={**ENTRY_DATA, CONF_REFRESH_TOKEN: "stored"}, unique_id=str(SID)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("alarm_control_panel.alarm_panel_home").state == "disarmed"
    assert hass.states.get("button.portail") is not None
    assert hass.states.get("sensor.entree_camera_status").state == "ONLINE"
    assert hass.states.get("sensor.alarm_panel_home_latest_clip").state.startswith("2023-11-14")
    assert hass.states.get("sensor.alarm_panel_home_latest_event").attributes["title"] == "logEvent.36.label2"

    await hass.services.async_call(BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: "button.portail"}, blocking=True)
    assert fake.commands == [{"type": "PULSE"}]

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    payloads = diagnostics["raw_api"]["payloads"]
    assert payloads["automatisms"]["automatisms"][0]["category"] == "GATE"
    assert payloads["installation"]["transmitter_connected"] is True
    assert "vendor-secret" not in str(diagnostics)

    assert await hass.config_entries.async_unload(entry.entry_id)
