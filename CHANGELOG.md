# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and semantic
versioning.

## [0.6.0b1] - Unreleased

Beta, for installations with automations or cameras. Requires pydaitem 0.3.0b1.

### Added

- Automations driven through the alarm, one device each: gates, garage doors and shutters
  as covers (or buttons when they only take an impulse), lights as lights, plugs and the
  rest as switches. Only the commands an automation lists are offered, and its state is
  read again 5 and 30 seconds after a command.
- Cameras as devices with a status sensor, and a "latest clip" timestamp sensor. Live
  video stays out of reach.
- The event log, for owner accounts: an `event` entity per new entry and a "latest event"
  sensor, read every fifteen minutes.
- Diagnostics now carry the raw answers of every read (automations, cameras, clips,
  widgets, scenarios, schedule, installation record, latest log entries) and a summary of
  what each automation became. Camera access details, uids, labels and addresses are
  masked.

### Changed

- Follows pydaitem 0.3.0b1: the coordinator reads the state and the inventory in one call,
  so a panel busy with the mobile app no longer freezes fault reporting.
- What happens on an error is decided by the error's remedy, as pydaitem states it. A
  refused alarm code now opens the reauth form instead of failing every cycle, and a
  missing right no longer opens it for nothing. Command failures show a translated message
  (English and French), and a command the panel did not confirm says to check the state
  before sending it again.
- The setup and reauth forms check the alarm code on the panel before saving it. A panel
  held by the mobile app is reported as such, not as a wrong code.
- Redaction comes from pydaitem, which applies it to its own dumps as well.
- "Enable debug logging" now captures the library's lines too (`loggers` in the manifest).
- Each call to the library is bounded to 60 s, the wait for the panel included, so a slow or
  hung Daitem server fails a cycle rather than stalling it.
- During an exit delay the five-second cycles read the state alone: the inventory waits for
  the delay to end, which spares the API a request per cycle.
- Diagnostics show the load the integration puts on the Daitem API: requests by endpoint,
  retries, panel sessions and how long they were held.
- When Daitem asks the client to back off, the alarm and the event log keep their last
  state instead of turning unavailable, and polling keeps its pace: pydaitem pauses on its
  own meanwhile.

### Notes

- How automations, cameras and clips behave is in the README, under "Automations, cameras
  and clips: beta". Installations without any of these read them every thirty minutes
  only.

### Release checklist

1. Publish pydaitem 0.3.0b1 on PyPI first: the manifest pins it.
2. Tag `v0.6.0b1` and publish it as a GitHub pre-release, so HACS offers it only to users
   who enable beta versions.

## [0.5.1] - 2026-09-14

### Fixed

- Setup no longer discovers the arming modes twice. The first refresh already runs
  discovery, and an explicit second call was left behind when discovery gained its retry,
  so every startup opened two panel sessions instead of one. The panel tolerates one at a
  time, so this doubled the contention at the moment it is most likely to bite, and a
  blocked discovery is exactly what leaves an installation on away-only arming. Seen in a
  real log, twice in the same second.

## [0.5.0] - 2026-09-14

### Added

- Firmware versions of the panel: the main software on the device page, and the radio and
  transmission module versions as hidden diagnostic sensors. Three values, two registry
  fields, hence the split. They were in the inventory payload all along.
- Remotes and keypads now appear as devices, hanging off the panel like the detectors. A
  live panel reports no fault for them, so their inhibition sensor is what they carry.
- An inhibition sensor per detector and control, visible by default. A neutralised
  detector is a hole in the protection while the system is armed, so it is not hidden
  behind a toggle like the faults are.
- Group membership: a hidden sensor on each detector, and a `groups` attribute on the alarm
  entity listing what each group contains, next to `active_groups`. The API gives numbers
  and no names, so numbers is what is shown. Controls report no group.

### Changed

- The panel device is now named "Alarm panel - {installation name}", "Centrale alarme -
  {nom}" in French, instead of "Alarm - {installation name}". "Alarm" read as the whole
  installation as easily as the box that drives it, and the app calls that box the
  centrale. Existing entity ids do not change, Home Assistant fixes them at creation. A
  fresh installation derives them from the new name, so the dashboard example moved with
  it.
- Pins `pydaitem==0.2.0`, which is where the firmware parsing lives.

### Fixed

- The panel device page no longer loses its model and serial number when the integration
  restarts on a cycle where the inventory could not be read. Home Assistant treats a device
  field passed as null as "clear it", so a single bad read wiped what the registry already
  held, and it stayed wiped until a reload got a good one.

## [0.4.0] - 2026-09-14

### Added

- Each fault sensor now has its own icon, switching between a healthy and a raised variant:
  a plug that unplugs, a shield that opens, an eye that closes. They used to share the one
  generic icon Home Assistant derives from the device class, which made the panel page a
  column of identical dots.

### Changed

- Fault sensors are translated. They carried a hardcoded English name, which is also why
  they stayed in English on a French installation, and it is what prevented them from
  having an icon of their own: both are keyed on the translation key they now have. Names
  update on the next reload. Existing entity ids do not change, but a fresh installation
  in French will derive them from the French names.
- The manual refresh button moved from the diagnostic section of the device page to the
  controls: pressing it acts on the panel rather than reporting on it. It stays hidden by
  default. Home Assistant reapplies the section on reload, so existing installations move
  too.

### Fixed

- A failed read cycle no longer greys the alarm out for a full five minutes. Home
  Assistant marks the entities unavailable as soon as a cycle fails, so a one-second
  glitch on the panel side cost a five-minute outage. Polling now drops to thirty seconds
  for up to five attempts, then returns to the normal pace, whether it recovered or the
  panel turned out to be properly unreachable. Seen for real: a single HTTP 500
  ("Unexpected null command response") among 765 successful reads over three days.
- Presence arming no longer disappears until a manual reload. Arming modes were read once
  at setup, and the alarm entity froze the modes it advertised at construction, so the
  panel only had to be busy for the second setup took to leave the installation on
  away-only arming. Discovery is now retried on the following cycles, and the Home button
  reappears on its own once it succeeds.

## [0.3.0] - 2026-09-13

### Added

- Diagnostics download on the integration, so a bug report can carry the coordinator state,
  the panel state, the inventory and the raw API payloads. Credentials, the alarm code and
  the refresh token are never included; serial numbers, device names and the email are only
  partially kept. Redaction matches key fragments rather than a fixed list, so a field
  nobody anticipated in a raw payload is redacted too.
- Repairs entries for the two degradations that used to be a log line only: the panel
  session held by another device for several cycles in a row, and arming mode discovery
  blocked at startup leaving only away arming.
- `docs/troubleshooting.md` and `docs/security-privacy.md`, a Lovelace dashboard example,
  GitHub issue templates, and an `info.md` shown in HACS instead of the full README.
- Brand icons, in the integration itself rather than through the Home Assistant brands
  repository. Dark theme variants too: the logo is black ink on transparency, so without
  them it is all but invisible on a dark background.

### Changed

- Releases are now created by pushing a `vX.Y.Z` tag. The workflow runs hassfest, HACS
  validation, ruff, mypy and the tests first, then takes the release notes from the
  matching CHANGELOG section, so the release body and the changelog cannot drift apart.

### Fixed

- The README listed per-group arming as a feature of the integration. Only the underlying
  pydaitem library offers it; the alarm entity exposes away and presence arming.

## [0.2.0] - 2026-09-13

### Changed

- The panel device is now named "Alarm - {installation name}" (translated), instead of
  just the installation name, so it stands out from the plain detector devices in the
  device list.

## [0.1.0] - 2026-09-13

First public release.

### Added

- `alarm_control_panel` entity: full arming, "presence" partial arming, per-group arming
  and disarming, with re-authentication triggered by a wrong master code instead of a
  generic setup failure with no way to correct it from the UI.
- Only Away and Home arming are offered: the only two modes whose meaning is verifiable
  (Away is the base command, Home/Presence is confirmed by its technical key). A panel
  armed through a named preset or a direct group command shows as unknown rather than a
  guessed "Night"/"Vacation" label pydaitem cannot vouch for.
- Panel and per-detector fault sensors (main/backup power, transmission media, tamper,
  battery, radio, masking...), each detector as its own device linked to the panel. Only
  battery and radio are visible by default; the others are still created and recorded,
  just hidden, since a detector typically reports six faults.
- A manual refresh button, hidden by default.
- Coordinator applying the measured session strategy: opportunistic read, no permanent
  session held, faster polling during arming delays, and last-known-state retention when
  the panel is busy with another device.
- Config flow with installation selection and re-authentication.
- English and French translations, entity icons.
- Pins `pydaitem>=0.1.1`. A test ties this pin to the library actually in use, since Home
  Assistant installs it from PyPI while CI develops against the same package.

### Notes

- Requires Home Assistant 2026.9.1 or later.
- The API exposes neither per-detector open/closed state nor the history for a restricted
  account.
