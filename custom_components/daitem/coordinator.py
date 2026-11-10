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
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pydaitem import (
    ArmMode,
    Automatism,
    Camera,
    Clip,
    DaitemError,
    DaitemSessionBusyError,
    DaitemSystem,
    Inventory,
    Snapshot,
    SystemStatus,
)

from .const import (
    ARMING_SCAN_INTERVAL,
    COMMAND_FOLLOW_UP_DELAYS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EXTRAS_IDLE_SCAN_INTERVAL,
    EXTRAS_SCAN_INTERVAL,
    RETRY_ATTEMPTS,
    RETRY_SCAN_INTERVAL,
)
from .errors import needs_reauth
from .repairs import async_set_arm_modes_issue, async_set_session_busy_issue

if TYPE_CHECKING:
    from .event_log import DaitemEventLogCoordinator

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
    automatisms: list[Automatism] = field(default_factory=list)
    cameras: list[Camera] = field(default_factory=list)
    clips: list[Clip] = field(default_factory=list)

    @property
    def latest_clip(self) -> Clip | None:
        dated = [clip for clip in self.clips if clip.taken_at is not None]
        return max(dated, key=lambda clip: clip.taken_at or 0) if dated else None

    def automatism(self, automatism_id: str) -> Automatism | None:
        return next((a for a in self.automatisms if a.id == automatism_id), None)


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
        self.panel_device_id: str | None = None
        """Registry id of the panel device, set by `async_setup_entry` before the platforms."""
        self._inventory_failed = False
        self._consecutive_session_busy = 0
        self._consecutive_failures = 0
        self._capabilities_discovered = False
        self._extras_due = 0.0
        self._extras_failing: set[str] = set()
        self._follow_ups: list[Callable[[], None]] = []
        self.event_log: DaitemEventLogCoordinator | None = None
        """Set by `async_setup_entry` when the account may read the event log."""

    @property
    def system_id(self) -> int:
        """Stable identifier for entity unique ids and the device registry."""
        return self.system.system_id

    @property
    def inventory(self) -> Inventory | None:
        """Latest inventory, or None before the first cycle or while it is unreadable."""
        return self.data.inventory if self.data else None

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
        snapshot = await self._read()
        inventory = self._pick_inventory(snapshot)
        status = snapshot.status
        err = snapshot.errors.get("status")
        if err is not None and needs_reauth(err):
            # A refused password or alarm code: polling cannot fix it, the reauth form asks
            # the user for it again.
            raise ConfigEntryAuthFailed(str(err)) from err
        if isinstance(err, DaitemSessionBusyError):
            # Another device is driving the alarm; that is not a failure. Keep the last
            # known state rather than making entities unavailable.
            _LOGGER.debug("Panel session busy, keeping last known state: %s", err)
            self._consecutive_session_busy += 1
            if self._consecutive_session_busy >= SESSION_BUSY_ISSUE_THRESHOLD:
                async_set_session_busy_issue(self.hass, self.system_id, active=True)
            if self.data is not None:
                self._note_cycle_delivered_data(self.data.status)
                return replace(self.data, inventory=inventory, session_busy=True)
            raise self._note_failed_cycle(f"Panel session busy: {err}") from err
        if err is not None or status is None:
            raise self._note_failed_cycle(f"Error communicating with Daitem: {err}") from err

        self._note_cycle_delivered_data(status)
        if self._consecutive_session_busy:
            self._consecutive_session_busy = 0
            async_set_session_busy_issue(self.hass, self.system_id, active=False)

        # Only once the read above has proved the panel reachable and free, so a retry
        # never adds contention of its own.
        if not self._capabilities_discovered:
            await self.async_load_capabilities()

        automatisms, cameras, clips = await self._read_extras()
        return DaitemData(
            status=status,
            inventory=inventory,
            last_success=dt_util.utcnow(),
            automatisms=automatisms,
            cameras=cameras,
            clips=clips,
        )

    async def _read_extras(self) -> tuple[list[Automatism], list[Camera], list[Clip]]:
        """Automations, cameras and clips, on their own slower pace.

        A list that fails to read keeps its previous value, as the inventory does, with one
        warning per outage. A failure is spelled out rather than swallowed, so the logs
        show which list could not be read.
        """
        previous = self.data
        if previous is not None and time.monotonic() < self._extras_due:
            return previous.automatisms, previous.cameras, previous.clips

        extras = await self.system.read_extras()
        automatisms = _pick(extras.automatisms, previous.automatisms if previous else [])
        cameras = _pick(extras.cameras, previous.cameras if previous else [])
        clips = _pick(extras.clips, previous.clips if previous else [])

        failing = set(extras.errors)
        for name in sorted(failing - self._extras_failing):
            _LOGGER.warning("Could not read the Daitem %s: %s", name, extras.errors[name])
        for name in sorted(self._extras_failing - failing):
            _LOGGER.info("Daitem %s readable again", name)
        self._extras_failing = failing

        found = bool(automatisms or cameras or clips)
        delay = EXTRAS_SCAN_INTERVAL if found or failing else EXTRAS_IDLE_SCAN_INTERVAL
        self._extras_due = time.monotonic() + delay
        return automatisms, cameras, clips

    def async_follow_up_command(self) -> None:
        """Read the automations again shortly after a command, then once more later.

        The command answer carries no state, and the app also waits for the next state
        update before showing the outcome.
        """
        for delay in COMMAND_FOLLOW_UP_DELAYS:
            self._follow_ups.append(async_call_later(self.hass, delay, self._follow_up))

    @callback
    def _follow_up(self, _now: datetime) -> None:
        self._extras_due = 0.0
        self.hass.async_create_task(self.async_request_refresh())

    async def async_shutdown(self) -> None:
        for cancel in self._follow_ups:
            cancel()
        self._follow_ups.clear()
        await super().async_shutdown()

    async def _read(self) -> Snapshot:
        """The state and the inventory, each failing on its own; the state alone mid-arming.

        The faults need no panel session, so a busy panel no longer freezes them. During an
        exit delay the cycle runs every few seconds to follow the state, and the faults can
        wait for it to settle: the inventory is not read again, which spares the API a
        request on each of those cycles.
        """
        if self.data is None or not self.data.status.is_arming:
            return await self.system.read_snapshot()
        snapshot = Snapshot(inventory=self.data.inventory)
        try:
            snapshot.status = await self.system.panel.read()
        except DaitemError as err:
            snapshot.errors["status"] = err
        return snapshot

    def _pick_inventory(self, snapshot: Snapshot) -> Inventory | None:
        """The inventory of this cycle, read every time because faults live in it.

        Fetching it once would freeze fault reporting at startup: a battery going flat or
        a tamper opening would never surface. It needs no panel session, so the extra call
        costs nothing and creates no contention with the mobile app. A failed read keeps
        the previous inventory.
        """
        inventory = snapshot.inventory
        err = snapshot.errors.get("inventory")
        if inventory is None:
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

        Thirty seconds is applied even mid-arming, where it is slower than the five-second
        arming pace. That is the deliberate trade: the entity is unavailable either way,
        and polling a panel that just failed every five seconds buys little. The arming
        pace is restored by the first cycle that delivers a state.
        """
        self._consecutive_failures += 1
        fast = self._consecutive_failures <= RETRY_ATTEMPTS
        self._set_interval(RETRY_SCAN_INTERVAL if fast else DEFAULT_SCAN_INTERVAL)
        return UpdateFailed(message)

    def _note_cycle_delivered_data(self, status: SystemStatus) -> None:
        """Leave the retry pace behind as soon as a cycle produces something usable.

        A busy session counts here too: it hands the last known state back rather than
        failing, so nothing is waiting to be recovered by polling faster.

        The pace returns to whatever the delivered state calls for, not to the normal
        interval: five seconds while an arming delay runs. Falling back to five minutes
        there would freeze the alarm on "arming" until long after the delay had settled.
        """
        self._consecutive_failures = 0
        self._schedule_for_state(status)

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
        the next cycle to refresh the UI. A command only gets that far once the panel has
        answered, which also settles any run of failed cycles behind it.
        """
        _LOGGER.debug("Publishing the state returned by the command: %s", status.state)
        self._note_cycle_delivered_data(status)
        if self.data is not None:
            data = replace(self.data, status=status, last_success=dt_util.utcnow(), session_busy=False)
        else:
            data = DaitemData(status=status, inventory=None, last_success=dt_util.utcnow())
        self.async_set_updated_data(data)


def _pick[T](fresh: list[T] | None, previous: list[T]) -> list[T]:
    """The fresh list when it was read, the previous one when its read failed."""
    return fresh if fresh is not None else previous
