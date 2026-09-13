# Daitem

Control a Daitem alarm (Atral "Topaze" platform) from Home Assistant: arming, disarming,
panel and per-detector fault sensors.

Unofficial, not affiliated with Daitem or the Atral group. It uses the private API of the
Daitem Secure mobile app, which can change without notice.

## What you get

- **Alarm panel entity** with full arming, presence (home) arming and disarming. Only these
  two arming modes are offered: what a named preset means cannot be verified, so it is never
  exposed under a guessed "night" or "vacation" label.
- **Fault sensors** on the panel (power supply, tamper, transmission media) and on each
  detector (battery, radio, masking, tamper). Battery and radio are visible by default, the
  rest are created but hidden to keep the entity list readable.
- **Manual refresh button**, hidden by default.
- **Repairs entries** when the panel session stays held by another device, or when arming
  mode discovery was blocked at startup.
- English and French translations.

## Setup

After installing and restarting Home Assistant:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=daitem)

Or: **Settings > Devices & services > Add integration > Daitem**.

Three values are asked for: the account email address, its password, and the **alarm code
tied to that account**, which is not necessarily the owner's master code. Creating a
dedicated secondary account in the Daitem app is recommended: actions from Home Assistant
then appear in the panel logbook under that account's code.

## Worth knowing before installing

**The panel accepts one session at a time, across all accounts.** While the Daitem app is
open on a phone, a command from Home Assistant fails with an explicit message. A secondary
account does not work around it. The integration never holds a session open and keeps the
last known state rather than going unavailable.

**No open/closed state per detector.** The API exposes faults only, not contacts.

**Five-minute latency by default**, faster during an arming delay.

## Documentation

- [Full README](https://github.com/tomahoax/ha-daitem)
- [Troubleshooting](https://github.com/tomahoax/ha-daitem/blob/main/docs/troubleshooting.md)
- [Security and privacy](https://github.com/tomahoax/ha-daitem/blob/main/docs/security-privacy.md)
- [Dashboard examples](https://github.com/tomahoax/ha-daitem/tree/main/lovelace)
