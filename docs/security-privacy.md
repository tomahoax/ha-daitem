# Security and privacy

You are handing this integration the credentials and the alarm code of your home. Here is
exactly what happens to them.

## This is unofficial

Not affiliated with, endorsed by, or supported by Daitem or the Atral group. It talks to the
private API of the Daitem Secure mobile app, reached by reverse engineering. That API is
non-contractual: it can change without notice with any app update, and break this
integration.

## It is not local

Every read and every command goes to Daitem's servers over the internet
(`appv3.tt-monitor.com`), authenticated against Atral's Keycloak (`auth.atraltech.com`).
There is no local fallback: if your internet connection or Daitem's service is down, Home
Assistant cannot read or control the alarm. The panel itself keeps working on its own, as
it does without Home Assistant.

## Where your credentials go

- Your email, password and alarm code are sent over HTTPS to Atral's authentication server
  and to the Daitem API, the same way the mobile app sends them. They never reach the author
  of this integration or any third party.
- They are stored by Home Assistant in its config entry, on your own hardware. Config
  entries live in `.storage/core.config_entries` as plain JSON, protected by file
  permissions only. A backup of your configuration therefore carries them in the clear,
  like any other Home Assistant integration that has to keep credentials.
- Authentication uses OAuth2 authorization code with PKCE. The refresh token obtained that
  way is kept alongside them, so a restart resumes the session instead of replaying the
  login form. Re-authenticating (after a password change, say) drops the stored refresh
  token rather than reusing it, so the session you meant to end really ends.

## What data is read

- The list of installations on the account, and the chosen installation's state.
- The device inventory: detectors and controls, with their name, serial number, group,
  inhibition status and faults.
- The arming presets defined on the installation, read at setup and retried on later
  polling cycles until the read succeeds.

The event history is not read: it is owner-only, and the account recommended here is a
restricted one.

## What ends up in logs and diagnostics

- No credential, alarm code or token is ever logged, at any level. Debug logging traces
  which path the code took, not what it sent.
- The diagnostics download redacts secrets outright and keeps serial numbers, device names
  and the email only partially. Redaction matches on key fragments rather than a fixed list,
  so a field nobody anticipated in a raw payload is redacted too.
- Review any log or diagnostics file before attaching it to a public issue anyway.

## Command safety

- Commands are sent exactly as the mobile app sends them. No experimental or guessed
  command is used.
- A command is never retried. A replayed request could arm or disarm the alarm twice, so a
  failure is surfaced to you rather than retried in the background. Only reads and session
  calls retry, and only for a dropped idle socket.
- Arming modes whose meaning cannot be verified are not exposed at all, rather than being
  guessed under a "night" or "vacation" label that might arm something other than what you
  expect.

## Recommended setup

Create a dedicated secondary account for Home Assistant in the Daitem app, with its own
alarm code. It does not avoid the single-session constraint, but actions from Home Assistant
then appear in the panel logbook under that account's code, distinct from yours, and the
account has no access to the history.
