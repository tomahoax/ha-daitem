"""Constants for the Daitem integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "daitem"

CONF_MASTER_CODE: Final = "master_code"
CONF_SYSTEM_ID: Final = "system_id"

#: Entry option set once `binary_sensor` has corrected the visibility of entities restored
#: from Home Assistant's `deleted_entities` record with their pre-default `hidden_by`
#: (see `binary_sensor._migrate_fault_visibility`), so it is never redone after that.
OPTION_FAULT_VISIBILITY_MIGRATED: Final = "fault_visibility_migrated"

#: Polling interval, in seconds.
#:
#: Five minutes, matching the reference Diagral integration. This is not a comfort
#: setting: the panel accepts only one session at a time, across all accounts. Fast
#: polling would hold that session permanently and lock the user out of the mobile app.
#: At five minutes a connect/read/disconnect cycle takes two to three seconds and leaves
#: the panel free about 99% of the time.
DEFAULT_SCAN_INTERVAL: Final = 300

#: Polling interval while an arming delay runs. The state settles on its own
#: (tempo -> on), so we follow closely and then fall back to the normal interval.
ARMING_SCAN_INTERVAL: Final = 5

#: Polling interval after a failed cycle. At the normal interval a one-second glitch on
#: the panel side leaves the alarm entity unavailable for five minutes, which is what the
#: user actually sees. Retrying at thirty seconds cuts that to about one.
RETRY_SCAN_INTERVAL: Final = 30

#: How many of those fast retries to make before returning to the normal interval. Past
#: this, the panel is not having a glitch, it is unreachable, and there is nothing to gain
#: from keeping up the pace.
RETRY_ATTEMPTS: Final = 5
