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

#: Automations, cameras and clips: re-read every five minutes on an installation that has
#: some, every thirty on one that has none, so the many installations without them pay
#: almost nothing for the feature. They are never read at the arming pace.
EXTRAS_SCAN_INTERVAL: Final = 300
EXTRAS_IDLE_SCAN_INTERVAL: Final = 1800

#: After an automation command, state reads at these delays: the app also waits for the
#: next state update before showing the outcome.
COMMAND_FOLLOW_UP_DELAYS: Final = (5, 30)

#: The event log is a slow, large, asynchronous read: fifteen minutes is plenty.
EVENT_LOG_SCAN_INTERVAL: Final = 900
