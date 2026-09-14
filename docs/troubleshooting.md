# Troubleshooting

## Known limitations, not bugs

**The panel accepts one session at a time, across all accounts.** While the Daitem app is
open on a phone, a command sent from Home Assistant fails with an explicit message, and the
state stops refreshing. A dedicated secondary account does not work around it. The
integration is built around this: it never holds a session open, reads the state without
opening one when another device already holds it, and keeps the last known state rather
than going unavailable.

**No open/closed state per detector.** The API exposes identity, group, inhibition and
faults, nothing else. A door opening only appears in the panel history, while armed.

**Five-minute latency by default.** Polling speeds up automatically during an arming delay,
then slows back down. Shortening the normal interval would hold the session almost
permanently and lock the mobile app out.

**No history.** Reading it is owner-only; a restricted account is refused.

## The alarm entity is unavailable

The entity goes unavailable when the coordinator has no usable state: either it has never
completed a successful read, or a read cycle failed for a reason other than a busy session.

A single failed cycle recovers on its own. Polling drops to thirty seconds for up to five
attempts after a failure, so a passing glitch on the panel side clears in about a minute
rather than lasting a full interval. Wait that long before doing anything.

1. Reload the integration (Settings > Devices & services > Daitem > three-dot menu >
   Reload). This forces an immediate cycle instead of waiting for the next one.
2. Check Settings > System > Repairs. A session held by another device for several cycles
   in a row raises an entry there.
3. If it persists, enable debug logging (below) and open an issue. Note that the first
   refresh right after a reload is not logged by Home Assistant even when it fails, which
   is why the logs can look empty.

## Only away arming is offered

Arming modes are read at setup. If the panel session was held by another device at that
moment, or the panel was briefly unreachable, discovery is skipped and only away arming is
available. A Repairs entry says so.

Discovery is retried on the following polling cycles, so this resolves itself: close the
Daitem app on your phone if it is open, and presence arming comes back within a few
minutes, along with the Repairs entry clearing. Reloading the integration only makes it
happen sooner.

Note that named presets beyond "presence" are never offered, by design: what a preset means
cannot be verified, so it is not exposed as a guessed "night" or "vacation" label.

## Enable debug logging

On the Daitem integration card, open the three-dot menu and choose **Enable debug logging**,
reproduce the problem, then **Disable debug logging**: Home Assistant downloads the log.

To enable it without a restart from Developer tools > Actions, call `logger.set_level` with:

```yaml
custom_components.daitem: debug
pydaitem: debug
```

## Download diagnostics

Settings > Devices & services > Daitem > your installation > **Download diagnostics**.

The file contains the coordinator state, the panel state, the device inventory and the raw
API payloads. Credentials, the alarm code and the refresh token are never included; serial
numbers, device names and the email are only partially kept. Have a look before attaching
it to an issue anyway.

## What to include in a bug report

- Integration version and Home Assistant version.
- Whether the integration uses the owner account or a restricted one.
- The diagnostics file.
- Debug logs covering the moment the problem happened, for anything intermittent.
