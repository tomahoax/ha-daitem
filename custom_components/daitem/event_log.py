"""The panel's event log, on its own coordinator.

Not named `logbook.py`: that file name is how an integration describes its events to Home
Assistant's own logbook, which is something else.

The read is asynchronous on the Daitem side, slow and large, and owner accounts only. A
restricted account gets a 403, after which the log is simply left out.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pydaitem import DaitemError, DaitemRateLimitedError, DaitemSessionBusyError, DaitemSystem, LogEntry, Remedy

from .const import DOMAIN, EVENT_LOG_SCAN_INTERVAL
from .coordinator import DaitemConfigEntry

_LOGGER = logging.getLogger(__name__)


class DaitemEventLogCoordinator(DataUpdateCoordinator[list[LogEntry]]):
    """Periodically read the event log, newest entry first as the API sends it."""

    config_entry: DaitemConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: DaitemConfigEntry, system: DaitemSystem) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} event log",
            update_interval=timedelta(seconds=EVENT_LOG_SCAN_INTERVAL),
        )
        self.system = system
        self.forbidden = False
        """True once the account was refused the log: it is not read again."""

    async def _async_update_data(self) -> list[LogEntry]:
        try:
            return await self.system.logbook.read()
        except DaitemError as err:
            if err.remedy is Remedy.NOT_PERMITTED:
                self.forbidden = True
                self.update_interval = None
                _LOGGER.info("The event log is for owner accounts only, so it is left out: %s", err)
                raise UpdateFailed(f"Event log refused: {err}") from err
            if isinstance(err, DaitemSessionBusyError | DaitemRateLimitedError) and self.data is not None:
                # Nothing is wrong with the entries already read: keep them for the next cycle.
                return self.data
            raise UpdateFailed(f"Could not read the event log: {err}") from err
