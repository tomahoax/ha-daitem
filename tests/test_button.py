"""The manual refresh button.

Its entity category decides which section of the device page it lands in, which is a
user-visible placement rather than an implementation detail, so it is worth pinning.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_refresh_button_sits_with_the_controls(
    hass: HomeAssistant, entry: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """Pressing it acts on the panel, so it is a control, not a diagnostic readout."""
    button = entity_registry.async_get("button.alarm_home_refresh")
    assert button is not None
    assert button.entity_category is None


async def test_refresh_button_stays_hidden_by_default(
    hass: HomeAssistant, entry: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """Being a control does not make it dashboard clutter: it is still opt-in.

    Note this only applies to a freshly created entity. Home Assistant reapplies the
    entity category on every registration, but takes `hidden_by` at creation only.
    """
    button = entity_registry.async_get("button.alarm_home_refresh")
    assert button is not None
    assert button.hidden_by is er.RegistryEntryHider.INTEGRATION
