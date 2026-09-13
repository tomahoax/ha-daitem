"""Data update coordinator for the Daitem integration.

Talks only to `DaitemSystem`, the library façade. It knows nothing of endpoints, the
session protocol, preset indices or raw API vocabulary, so a change in the Daitem API is
absorbed by the library alone.

The session strategy it relies on was validated by measurement:

- **Opportunistic read**: the façade reads without opening a session when another device
  already holds one, and opens a short-lived session otherwise.
- **No permanent session**: the panel accepts only one, so holding it would lock the
  mobile app out.
- **Delay tracking**: poll faster while an arming delay runs, then slow back down.
- **Graceful degradation**: if another device holds the session, keep the last known state
  instead of marking entities unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pydaitem import (
    ArmMode,
    DaitemAuthError,
    DaitemError,
    DaitemForbiddenError,
    DaitemSessionBusyError,
    DaitemSystem,
    Inventory,
    SystemStatus,
)

from .const import ARMING_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type DaitemConfigEntry = ConfigEntry[DaitemCoordinator]


@dataclass(slots=True)
class DaitemData:
    """Snapshot handed to the entities."""

    status: SystemStatus
    inventory: Inventory | None
    last_success: datetime
    session_busy: bool = False
    """True when the last cycle failed because another device held the session."""


class DaitemCoordinator(DataUpdateCoordinator[DaitemData]):
    """Periodically fetch the alarm state and the device faults."""

    config_entry: DaitemConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: DaitemConfigEntry,
        system: DaitemSystem,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.system = system
        self.arm_modes: frozenset[ArmMode] = frozenset({ArmMode.AWAY})
        self._inventory_failed = False

    @property
    def system_id(self) -> int:
        """Stable identifier for entity unique ids and the device registry."""
        return self.system.system_id

    async def async_load_capabilities(self) -> None:
        """Discover the arming modes this installation supports, once at setup."""
        try:
            self.arm_modes = await self.system.capabilities.arm_modes()
        except DaitemError as err:
            # Defensive only: the façade swallows discovery failures itself today and
            # returns away alone. Kept in case that contract changes.
            _LOGGER.warning(
                "Could not discover the arming modes, only away arming will be offered. "
                "Reload the integration to try again: %s",
                err,
            )
            _LOGGER.debug("Full error: %s", err, exc_info=True)
            return

        if not self.system.capabilities.discovered:
            _LOGGER.warning(
                "Arming mode discovery was blocked, only away arming will be offered. "
                "This can happen when another device is holding the panel session, or "
                "when the panel was briefly unreachable. Reload the integration once "
                "the panel is reachable and free to get presence arming back."
            )

    async def _async_update_data(self) -> DaitemData:
        try:
            status = await self.system.read_status()
        except (DaitemAuthError, DaitemForbiddenError) as err:
            # A 403 on connect() means a wrong master code, not a restricted account: the
            # reauth form asks for it again, unlike a plain retry loop.
            raise ConfigEntryAuthFailed(str(err)) from err
        except DaitemSessionBusyError as err:
            # Another device is driving the alarm; that is not a failure. Keep the last
            # known state rather than making entities unavailable.
            _LOGGER.debug("Panel session busy, keeping last known state: %s", err)
            if self.data is not None:
                return DaitemData(
                    status=self.data.status,
                    inventory=self.data.inventory,
                    last_success=self.data.last_success,
                    session_busy=True,
                )
            raise UpdateFailed(f"Panel session busy: {err}") from err
        except DaitemError as err:
            raise UpdateFailed(f"Error communicating with Daitem: {err}") from err

        self._schedule_for_state(status)
        return DaitemData(
            status=status,
            inventory=await self._read_inventory(),
            last_success=dt_util.utcnow(),
        )

    async def _read_inventory(self) -> Inventory | None:
        """Refresh the inventory every cycle, because faults live in it.

        Fetching it once would freeze fault reporting at startup: a battery going flat or
        a tamper opening would never surface. It needs no panel session, so the extra call
        costs nothing and creates no contention with the mobile app.
        """
        try:
            inventory = await self.system.read_inventory()
        except DaitemError as err:
            if not self._inventory_failed:
                # Warn once per outage rather than on every cycle.
                _LOGGER.warning("Could not read the Daitem device inventory: %s", err)
                self._inventory_failed = True
            return self.data.inventory if self.data else None

        if self._inventory_failed:
            _LOGGER.info("Daitem device inventory readable again")
            self._inventory_failed = False
        return inventory

    def _schedule_for_state(self, status: SystemStatus) -> None:
        """Speed polling up during an arming delay, slow it down once settled."""
        wanted = ARMING_SCAN_INTERVAL if status.is_arming else DEFAULT_SCAN_INTERVAL
        target = timedelta(seconds=wanted)
        # Ignored below: mypy does not follow Home Assistant sources
        # (follow_imports = skip) so it cannot type update_interval.
        if self.update_interval != target:  # type: ignore[has-type]
            _LOGGER.debug("Polling interval set to %ss", wanted)
            self.update_interval = target

    async def async_apply_command_result(self, status: SystemStatus) -> None:
        """Publish the state returned by a command straight away.

        Command responses already carry the full state, so there is no need to wait for
        the next cycle to refresh the UI.
        """
        _LOGGER.debug("Publishing the state returned by the command: %s", status.state)
        self._schedule_for_state(status)
        self.async_set_updated_data(
            DaitemData(
                status=status,
                inventory=self.data.inventory if self.data else None,
                last_success=dt_util.utcnow(),
            )
        )
