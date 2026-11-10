# Home Assistant gaps

What the integration could still build on pydaitem, ordered by value for users, then by
effort. The API itself (every call the Daitem Secure app makes, its states, error codes and
retry rules) is documented in pydaitem's [API map](https://github.com/tomahoax/pydaitem/blob/main/docs/api/README.md).
This page only covers the Home Assistant side.

**Done in 0.6.0b1 (beta):** automations (covers, buttons, lights, switches), cameras as
devices with their status, the latest clip sensor and the event log. They are marked below,
and how they behave is in the README.

## Adopting pydaitem 0.3.0

pydaitem 0.3.0 also brings these, which the integration does not use yet:

| Library change | What the integration should do |
|---|---|
| ~~`DaitemBadCodeError` (the panel refused the alarm code)~~ | Done in 0.6.0b1: the reauth form asks for the code |
| `PanelState.MAINTENANCE` (installation or test mode) | Show the alarm entity as unavailable, or expose the mode as an attribute |
| `PanelState.ARMED_PARTIAL_2` now mapped from `partial2` | Give the second named preset an alarm state (`armed_custom_bypass`) |
| `DaitemTransmitterOfflineError` | Mark entities unavailable with that reason, without opening a session |
| ~~`DaitemRateLimitedError`~~ | Done in 0.6.0b1: the last state is kept and the pace unchanged, since pydaitem pauses on its own |
| ~~`DaitemCommandError.command_status` is `TIMEOUT`~~ | Done in 0.6.0b1: the message says to check the state before sending again |

## New features, from most to least useful

| Feature | Calls | Home Assistant entity | Notes |
|---|---|---|---|
| ~~Transmitter connectivity~~ | `POST /installation/isConnected` | `binary_sensor` (connectivity) | Done in 0.6.0b1 |
| ~~Automations (shutters, gates, lights, plugs)~~ | `GET /v5/.../automatisms`, `POST .../automatisms/{id}/command` | `cover`, `light`, `switch` | Done in 0.6.0b1. Automations exposed as widgets only (`sendAutomationWidgetCommand`) are not yet |
| Group arming | `sendGroupCommand` (already in pydaitem) | `switch` per group | Groups are already read |
| Device inhibition | `PATCH /v1/.../products/{serialNumber}` | `switch` per inhibitable device | The inventory already says which devices can be inhibited |
| Arming schedule | schedule calls (mostly in pydaitem) | `switch` for the schedule, programs as attributes | |
| ~~Scenarios~~ | `GET /v6/.../scenarios`, `startScenarioWidgetCommand` | `button` per manual scenario | Done in 0.6.0b1 |
| ~~Event log~~ | logbook calls (in pydaitem) | `event` entity, last event `sensor` | Done in 0.6.0b1. Readable titles need the app's translation keys mapped |
| Recorded clips | `GET /v6/.../videos`, `.../mpeg4`, capture calls | `image` or media source | Latest clip sensor done in 0.6.0b1. Playback and a capture button remain |
| Firmware | `updateFirmware` | `update` | Versions already exposed. Risky to trigger remotely |
| Alerts | `startAlertWidgetCommand` | `button`, behind confirmation | Panic or silent alert. Think twice |

Out of scope: account and user administration, codes and rights, push registration (Home
Assistant cannot receive the app's pushes), widget layout, marketing, feedback, installer
access and test mode.


## Cameras, clips and automations: what the app does

What the Daitem Secure 6.0.3 app does with each, and which of these an integration can
reproduce.

### Cameras: live video is out of reach

| Camera type | What the app does | For Home Assistant |
|---|---|---|
| `DAHUA` (local) | Does not play it: hands over to the separate Daitem Capture app | Nothing to reuse. Add the camera to Home Assistant directly (ONVIF, RTSP), outside Daitem |
| `DAHUA_CLOUD` | Plays it peer to peer through the Dahua SDK bundled in the app | No stream URL ever comes from Topaze. A `camera` entity would need Dahua's SDK: not reproducible |
| `DAITEM_CLOUD` | No live player | Unknown |

### Recorded clips: reachable

The app plays a clip straight from Topaze, with the same Bearer token as every other call:

`https://appv3.tt-monitor.com/topaze/v5/systems/{systemId}/videos/{category}/{deviceUid}/{filmId}/mpeg4`

- `category` is `DETECTOR`, `CAMERA` or `ARCHIVE`, from the clip's own category.
- A clip without a `deviceUid` is fetched with `0` in its place.
- A capture on demand is a `POST .../videos/capture/carir/{carirId}`, then polling the transaction.

So an `image` entity (last frame of the last alarm clip), a media source listing the clips, and a
"capture now" button per image detector are all realistic.

### Automations: the app's own rules

| Rule | For Home Assistant |
|---|---|
| The automation widget has two forms: `onOff` shows an ON and an OFF button, `launch` a single Activate button | `onOff` maps to a `switch` or `light`, `launch` to a `button` |
| The widget sends `on`, `off` or `launch` | The same three values for `sendAutomationWidgetCommand` |
| A command stays pending until the next state update, and its button is disabled meanwhile | Keep the last known state and mark the entity busy, rather than guessing the outcome |
| Each automation lists the commands it accepts (`ON`, `OFF`, `UP`, `DOWN`, `STOP`, `POSITION`, `STEP_UP`, `STEP_DOWN`, `TIMER`, `PULSE`, `SWITCH`) and reports `ON`, `OFF` or `POSITION` with a position | Offer only `availableCommands`: open, close, stop and set position on a `cover` when present |

On the library side, pydaitem would need the clip URL, the capture calls and the automation
commands. They belong in its [API map](https://github.com/tomahoax/pydaitem/blob/main/docs/api/README.md).

## Entity by entity

Where the integration stands on each entity of the app, and what it could add. Entities with
nothing to add are left out. The library side of each one is in pydaitem's
[entities](https://github.com/tomahoax/pydaitem/blob/main/docs/api/entities.md).

| Entity | In Home Assistant today | Next for the integration |
|---|---|---|
| System | Control panel device, transmitter connectivity sensor | Done in 0.6.0b1 |
| SystemState | alarm_control_panel state | armed_custom_bypass or attributes for the second preset; maintenance shown during test mode |
| Group | Group sensor per detector, groups on the alarm entity | One switch per group (arm_groups already exists) |
| Alarm | None | Create alert and scenario entities only when the panel allows them |
| SystemCode | None | Config flow checks the code length |
| SystemProducts | Inventory read every cycle, a device per family | Done in 0.6.0b1 |
| Sensor | Device, fault sensors, inhibition sensor | Inhibition switch per inhibitable detector |
| Siren | Device with its fault sensors | Done in 0.6.0b1 |
| Transmitter | Transmitter firmware sensor | Transmitter device with its faults |
| Transceiver | Device with its fault sensors | Done in 0.6.0b1 |
| Box | Device with its faults and software version | Done in 0.6.0b1 |
| FireTrigger | `binary_sensor` (smoke) per trigger | Done in 0.6.0b1 |
| PpmsTrigger | `binary_sensor` (safety) per trigger | Done in 0.6.0b1 |
| Firmware | Firmware version sensors | update entity per device with a newer firmware |
| Automatism | `cover`, `light`, `switch` or `button` per automation | Done in 0.6.0b1 |
| Scenario | `button` per manual scenario | Done in 0.6.0b1 |
| ScenarioAction | Action count on the scenario button | The actions themselves, once their shape is known |
| ProgramList | None | switch to turn the schedule on and off |
| Program | None | Programs as attributes of the schedule switch |
| Logbook | `event` entity and last event sensor (owner accounts) | Done in 0.6.0b1 |
| FilmDetails | None | image entity with the last clip frame |
| Right | None | Hide what the account may not do |
| WidgetItem | Preset ids | Preset names from customName |
