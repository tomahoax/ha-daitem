# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and semantic
versioning.

## [Unreleased]

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
