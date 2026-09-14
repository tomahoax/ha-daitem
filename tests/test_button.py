"""The manual refresh button.

Its entity category decides which section of the device page it lands in, which is a
user-visible placement rather than an implementation detail, so it is worth pinning.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

#: Also referenced by `lovelace/example-dashboard.yaml`, so a rename breaks the example.
ENTITY_ID = "button.alarm_panel_home_refresh"


@pytest.fixture
async def button(entry: MockConfigEntry, entity_registry: er.EntityRegistry) -> er.RegistryEntry:
    """The registry row of the refresh button, on a freshly configured installation."""
    registered = entity_registry.async_get(ENTITY_ID)
    assert registered is not None
    return registered


async def test_refresh_button_sits_with_the_controls(button: er.RegistryEntry) -> None:
    """Pressing it acts on the panel, so it is a control, not a diagnostic readout."""
    assert button.entity_category is None


async def test_refresh_button_stays_hidden_by_default(button: er.RegistryEntry) -> None:
    """Being a control does not make it dashboard clutter: it is still opt-in.

    Note this only applies to a freshly created entity. Home Assistant reapplies the
    entity category on every registration, but takes `hidden_by` at creation only.
    """
    assert button.hidden_by is er.RegistryEntryHider.INTEGRATION


async def test_pressing_it_only_asks_for_a_refresh(
    hass: HomeAssistant, entry: MockConfigEntry, button: er.RegistryEntry
) -> None:
    """A press queues a refresh instead of forcing a read.

    The panel tolerates a single session at a time, so a hidden control someone puts on a
    dashboard and taps repeatedly must go through the coordinator debouncer.
    """
    with patch.object(entry.runtime_data, "async_request_refresh") as request_refresh:
        await hass.services.async_call(BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True)

    assert request_refresh.await_count == 1
