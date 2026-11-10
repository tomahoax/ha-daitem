# Daitem for Home Assistant

**Unofficial** Home Assistant integration for Daitem alarms (Atral "Topaze" platform). It
builds on the [pydaitem](https://github.com/tomahoax/pydaitem) library, which consumes the
private API of the Daitem Secure mobile app.

> **Not affiliated with Daitem or the Atral group.** The API it uses is private and
> non-contractual: it may change without notice with any app update. Use it at your own
> risk, on your own hardware and with your own account.

## Features

- `alarm_control_panel` entity: full arming, "presence" partial arming, disarming.
- **Fault** sensors on the panel (power supply, tamper, transmission media) and on each
  detector (battery, radio, masking, tamper). Each has its own icon, which switches when
  the fault is raised, so a problem is visible at a glance.
- Manual refresh button, with the controls, hidden by default.
- **Repairs** entries when the panel session stays held by another device, or when arming
  mode discovery was blocked at startup. Both clear themselves once the panel is reachable
  and free again.
- **Inhibition** sensor per device: a detector deliberately neutralised is visible without
  going looking for it.
- Remotes, keypads, sirens, transmitters, transceivers and the box exposed as devices too,
  as soon as they report a fault or can be inhibited, and the panel's firmware versions.
- Fire and PPMS triggers say whether they have gone off (`smoke` and `safety` sensors).
- **Transmitter** connectivity sensor, read without a panel session. It keeps answering
  while the alarm is unavailable, which tells an offline box from a Daitem outage.
- Group membership, as a sensor per detector and as a mapping on the alarm entity.
- Diagnostics download, with credentials and codes redacted.
- English and French throughout, entity names included.

**Beta (0.6.0b1): automations, cameras and the event log.** Please try it and send back
your diagnostics (see below).

- **Automations** driven through the alarm, each as its own device: a gate, garage door or
  shutter becomes a `cover` (open, close, stop and position as it allows), one that only
  takes an impulse a `button`, a light a `light`, a plug a `switch`.
- **Cameras** as devices with their status. Live video is not available: the Daitem app
  plays it through the camera vendor's own SDK, which Home Assistant cannot use. Add an IP
  camera to Home Assistant directly (ONVIF, RTSP) for its stream.
- **Latest clip** sensor: when the last recorded clip was taken, on alarm or on demand,
  and from which device.
- **Event log** (owner accounts): an `event` entity firing for every new entry, and a
  "latest event" sensor. Entry titles are the Daitem app's own keys
  (`logEvent.36.label2`), not readable text yet.
- **Scenarios** run by hand, as a button each. A scenario performs the actions the
  installer gave it, which may arm or disarm the alarm, exactly as from the app.

## Limitations, worth reading before installing

These come from the API, not from the integration.

**One session at a time on the panel, across all accounts.** Creating a secondary account
does not work around it. While you use the mobile app, a command
sent from Home Assistant fails with an explicit message. The integration is designed to
minimise this: it never holds a session open, reads the state without opening one when
your phone already holds it, and keeps the last known state rather than going unavailable.

**No per-detector open/closed state.** The API does not expose it. Only faults (battery,
tamper, radio, masking) are available. A door opening only appears in the panel history,
while the system is armed.

**Five-minute latency by default.** An alarm trigger only reaches Home Assistant on the
next cycle. The interval is not a comfort setting: shortening it would hold the session
permanently and lock out your mobile app. Polling does speed up on its own in the two
cases where waiting five minutes would be unreasonable: during an arming delay, and after
a failed read, so a passing glitch on the panel side clears in about a minute instead of
leaving the alarm greyed out for a full cycle.

**Event log for owners only.** A restricted account is refused, so its entities are left
out.

**Scenarios: beta.** They are read every thirty minutes, never during an exit delay, since
the read may hold the panel. A scenario added in the app appears within thirty minutes. Scenarios
the panel runs on its own (on fire, on intrusion) get no button, and one switched off in
the app shows as unavailable. A button press runs the scenario without asking for the code,
like the alarm entity: keep it off dashboards others can reach if it disarms.

**Automations, cameras and clips: beta.** They work as follows:

- An opening that reports `OFF` is closed, `ON` is open, and a reported position runs from
  0 (closed) to 100 (open).
- A gate or garage door that only takes an impulse has no state worth trusting, so it is a
  button rather than a cover.

Every automation entity declares an assumed state, so both directions stay available even
if the state reads wrong. They are read every five minutes, and every thirty minutes on an
installation that has none, so installations without them pay almost nothing.

**Added in the app, appears in Home Assistant.** A detector or siren learnt by the
installer, an automation, a scenario or a camera added in the Daitem app gets its entities
on the next cycle that reads it, without reloading the integration: within five minutes for
devices, automations and cameras (thirty on an installation that had no automation or
camera yet), thirty for scenarios.

**Testing the beta.** Download the diagnostics (Settings, Devices and services, Daitem, the
three dots, Download diagnostics) and attach the file to an issue. It now includes the raw
answers for automations, cameras, clips, widgets and scenarios, with names, serial numbers,
e-mail addresses and camera access details masked. Read it before posting anyway.

## Installation

### Through HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tomahoax&repository=ha-daitem&category=integration)

Click the badge above, install "Daitem" from HACS, then restart Home Assistant.

<details>
<summary>Manual HACS steps, if the badge does not work</summary>

1. In Home Assistant, open HACS, then Integrations.
2. Open the ⋮ menu (top right corner), then "Custom repositories".
3. Repository: `https://github.com/tomahoax/ha-daitem`, category: "Integration". Add it.
4. Search for "Daitem" in HACS, download it, then restart Home Assistant.

</details>

### Manually, without HACS

1. Download the [latest release](https://github.com/tomahoax/ha-daitem/releases) archive.
2. Extract `custom_components/daitem` into the `custom_components` folder of your
   configuration.
3. Restart Home Assistant.

Home Assistant installs the `pydaitem` library automatically from PyPI, based on the
`requirements` field of the manifest.

## Configuration

Settings, then Devices and services, then Add integration, then "Daitem".

Three values are asked for: the account email address, its password, and the **alarm code
tied to that account**. Note that this is not necessarily the owner's master code: a
restricted user has their own.

Creating a **dedicated secondary account** for Home Assistant in the Daitem app is
recommended. It does not avoid the session conflict, but it makes actions attributable:
they appear in the panel logbook under that account's code, distinct from yours.

Entity ids are derived from the entity names, which are translated, so a Home Assistant
running in French names them in French
(`binary_sensor.centrale_alarme_la_chapelle_alimentation_principale`). The examples in
this repository use the English ids. Settings > Devices & services > Daitem > your
installation lists the real ones.

## State mapping

| Daitem state | Home Assistant state |
|--------------|----------------------|
| `off` | `disarmed` |
| `tempo`, `tempogroup` | `arming` |
| `on` | `armed_away` |
| `presence` | `armed_home` |
| anything else (a named preset, or a direct group activation) | `unknown` |

Only `presence` is confirmed by its technical key. What a named preset or a direct group
activation actually means is a guess the integration cannot vouch for, so it is shown as
an honest `unknown` rather than a label (such as "night" or "vacation") that might be
wrong.

## Documentation

- [Troubleshooting](docs/troubleshooting.md): unavailable entity, only away arming offered,
  debug logs, diagnostics.
- [Security and privacy](docs/security-privacy.md): where your credentials go, what is read,
  what ends up in logs.
- [Dashboard examples](lovelace/): stock Lovelace cards to copy.
- [Home Assistant gaps](docs/home-assistant-gaps.md): what the integration could still build
  on pydaitem. Every call the Daitem Secure app makes is in pydaitem's
  [API map](https://github.com/tomahoax/pydaitem/blob/main/docs/api/README.md).

## Development

To work on the library and the integration side by side, without going through PyPI:

```bash
pip install -e ../pydaitem
```

Home Assistant will not reinstall a dependency that is already satisfied, so keep the
local `pydaitem` version aligned with the one pinned in `manifest.json`; otherwise HA
fetches PyPI and overwrites your editable install.

## Licence

MIT.
