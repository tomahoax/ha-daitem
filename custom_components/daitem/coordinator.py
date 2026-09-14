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
- **Fast retry**: a failed cycle does mark them unavailable, so poll every thirty seconds
  for a short while afterwards rather than leaving the alarm greyed out for a full
  interval over a glitch that lasted a second.
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

from .const import (
    ARMING_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    RETRY_ATTEMPTS,
    RETRY_SCAN_INTERVAL,
)
from .repairs import async_set_arm_modes_issue, async_set_session_busy_issue

_LOGGER = logging.getLogger(__name__)

#: Consecutive busy cycles before the Repairs entry appears. Someone using the mobile app
#: for a cycle or two is ordinary; a session still held after this long is usually one
#: leaked by a client that stopped without disconnecting, and the user has no other way of
#: knowing why the state stopped moving.
SESSION_BUSY_ISSUE_THRESHOLD = 3

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
        self._consecutive_session_busy = 0
        self._consecutive_failures = 0
        self._capabilities_discovered = False

    @property
    def system_id(self) -> int:
        """Stable identifier for entity unique ids and the device registry."""
        return self.system.system_id

    async def async_load_capabilities(self) -> None:
        """Discover the arming modes this installation supports.

        Retried on later cycles until it succeeds, because the panel only has to be busy
        for the one second this runs at setup to leave the installation on away-only
        arming. That used to last until somebody reloaded the integration by hand.
        """
        try:
            self.arm_modes = await self.system.capabilities.arm_modes()
        except DaitemError as err:
            # Defensive only: the façade swallows discovery failures itself today and
            # returns away alone. Kept in case that contract changes.
            _LOGGER.warning(
                "Could not discover the arming modes, only away arming will be offered "
                "until a later cycle succeeds: %s",
                err,
            )
            _LOGGER.debug("Full error: %s", err, exc_info=True)
            return

        discovered = self.system.capabilities.discovered
        if discovered and not self._capabilities_discovered:
            _LOGGER.info("Arming mode discovery succeeded, offering: %s", sorted(m.value for m in self.arm_modes))
        self._capabilities_discovered = discovered
        async_set_arm_modes_issue(self.hass, self.system_id, active=not discovered)
        if not discovered:
            _LOGGER.warning(
                "Arming mode discovery was blocked, only away arming will be offered for "
                "now. This can happen when another device is holding the panel session, "
                "or when the panel was briefly unreachable. It is retried on the next "
                "cycles, so presence arming comes back on its own."
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
            self._consecutive_session_busy += 1
            if self._consecutive_session_busy >= SESSION_BUSY_ISSUE_THRESHOLD:
                async_set_session_busy_issue(self.hass, self.system_id, active=True)
            if self.data is not None:
                self._note_cycle_delivered_data()
                return DaitemData(
                    status=self.data.status,
                    inventory=self.data.inventory,
                    last_success=self.data.last_success,
                    session_busy=True,
                )
            raise self._note_failed_cycle(f"Panel session busy: {err}") from err
        except DaitemError as err:
            raise self._note_failed_cycle(f"Error communicating with Daitem: {err}") from err

        self._note_cycle_delivered_data()
        if self._consecutive_session_busy:
            self._consecutive_session_busy = 0
            async_set_session_busy_issue(self.hass, self.system_id, active=False)

        # Only once the read above has proved the panel reachable and free, so a retry
        # never adds contention of its own.
        if not self._capabilities_discovered:
            await self.async_load_capabilities()

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

    def _note_failed_cycle(self, message: str) -> UpdateFailed:
        """Poll faster for a while after a failure, so the outage is a minute, not five.

        Home Assistant makes the entities unavailable on a failed cycle, so at the normal
        interval a one-second glitch on the panel side costs five minutes of a greyed-out
        alarm. Retrying every thirty seconds recovers from that in about one.

        Past `RETRY_ATTEMPTS` the panel is not glitching, it is unreachable, so the pace
        returns to normal rather than hammering it for as long as the outage lasts.
        """
        self._consecutive_failures += 1
        fast = self._consecutive_failures <= RETRY_ATTEMPTS
        self._set_interval(RETRY_SCAN_INTERVAL if fast else DEFAULT_SCAN_INTERVAL)
        return UpdateFailed(message)

    def _note_cycle_delivered_data(self) -> None:
        """Leave the retry pace behind as soon as a cycle produces something usable.

        A busy session counts here too: it hands the last known state back rather than
        failing, so nothing is waiting to be recovered by polling faster.
        """
        if not self._consecutive_failures:
            return
        self._consecutive_failures = 0
        self._set_interval(DEFAULT_SCAN_INTERVAL)

    def _set_interval(self, seconds: int) -> None:
        target = timedelta(seconds=seconds)
        # Ignored below: mypy does not follow Home Assistant sources
        # (follow_imports = skip) so it cannot type update_interval.
        if self.update_interval != target:  # type: ignore[has-type]
            _LOGGER.debug("Polling interval set to %ss", seconds)
            self.update_interval = target

    def _schedule_for_state(self, status: SystemStatus) -> None:
        """Speed polling up during an arming delay, slow it down once settled."""
        self._set_interval(ARMING_SCAN_INTERVAL if status.is_arming else DEFAULT_SCAN_INTERVAL)

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
