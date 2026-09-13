# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and semantic
versioning.

## [Unreleased]

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
