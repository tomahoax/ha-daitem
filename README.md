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
  detector (battery, radio, masking, tamper).
- Manual refresh button, hidden by default.
- **Repairs** entries when the panel session stays held by another device, or when arming
  mode discovery was blocked at startup.
- Diagnostics download, with credentials and codes redacted.

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
permanently and lock out your mobile app. Polling speeds up automatically during arming
delays.

**No history.** Reading it is owner-only; a restricted account is refused.

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
