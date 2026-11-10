"""Whether the transmitter, and so the panel, can be reached, on its own coordinator.

The read needs no panel session, so it never keeps the mobile app out. It runs apart from
the main coordinator on purpose: when the panel cannot be read, the alarm entities turn
unavailable, and this sensor is what tells an offline box from a Daitem outage. On its
coordinator it stays readable through such a failure.

The first read costs two more requests (the account's installations, then the installation
record that carries the transmitter id), which pydaitem keeps for the next ones.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pydaitem import DaitemError, DaitemRateLimitedError, DaitemSystem, Remedy

from .const import CONNECTIVITY_SCAN_INTERVAL, DOMAIN
from .coordinator import DaitemConfigEntry

_LOGGER = logging.getLogger(__name__)


class DaitemConnectivityCoordinator(DataUpdateCoordinator[bool | None]):
    """Periodically ask whether the transmitter is online. None when the API does not say."""

    config_entry: DaitemConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: DaitemConfigEntry, system: DaitemSystem) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} connectivity",
            update_interval=timedelta(seconds=CONNECTIVITY_SCAN_INTERVAL),
        )
        self.system = system
        self.forbidden = False
        """True once the account was refused the read: it is not read again."""
        self._read_once = False
        """Whether a read ever succeeded. `data` cannot tell: None is a valid answer."""

    async def _async_update_data(self) -> bool | None:
        try:
            online = await self.system.panel.transmitter_online()
        except DaitemError as err:
            if err.remedy is Remedy.NOT_PERMITTED:
                self.forbidden = True
                self.update_interval = None
                _LOGGER.info("This account may not read the transmitter's connectivity, so it is left out: %s", err)
                raise UpdateFailed(f"Connectivity refused: {err}") from err
            if isinstance(err, DaitemRateLimitedError) and self._read_once:
                return self.data
            raise UpdateFailed(f"Could not read the transmitter's connectivity: {err}") from err
        self._read_once = True
        return online
