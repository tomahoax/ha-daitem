"""Diagnostics download, meant to be safe to attach to a GitHub issue.

Everything here goes through pydaitem's redaction, the one the library applies to its own
dumps: the credentials and the refresh token never appear, serial numbers and device names
are kept only partially.

The raw answers of every read that matters (automations, cameras, clips, widgets,
scenarios, the event log...) are fetched again when the file is downloaded, through
`DaitemSystem.collect_raw`. They are what a tester with hardware nobody else has sends
back, and what settles how those devices are supported.

Both a structured summary and the raw API payloads are included. The summary answers the
usual questions (is the coordinator updating, is the panel session held by another device,
which arming modes were discovered); the raw payloads are where an unmapped state or a
renamed field shows up when the Daitem side changes, which the summary would hide by
construction.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from pydaitem import DaitemError, Inventory, SystemStatus, redact, redact_identifier

from .automatism import entity_kind
from .const import CONF_SYSTEM_ID
from .coordinator import DaitemConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: DaitemConfigEntry) -> dict[str, Any]:
    """Return the redacted state of one installation."""
    # `runtime_data` is unset while an entry is still retrying its setup, which is exactly
    # when diagnostics are most likely to be requested. Degrade rather than raise.
    coordinator = getattr(entry, "runtime_data", None)
    data = getattr(coordinator, "data", None)

    diagnostics: dict[str, Any] = {
        "entry": {
            "title": redact_identifier(entry.title),
            "email": redact_identifier(str(entry.data.get(CONF_EMAIL, ""))),
            "system_id": entry.data.get(CONF_SYSTEM_ID),
            "options": redact(dict(entry.options)),
            "state": str(entry.state),
        },
        "coordinator": {
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "update_interval_seconds": _update_interval_seconds(coordinator),
            "arm_modes": sorted(mode.value for mode in getattr(coordinator, "arm_modes", frozenset())),
            "arm_modes_discovered": _arm_modes_discovered(coordinator),
            "has_data": data is not None,
        },
    }

    if data is None:
        return diagnostics

    diagnostics["state"] = {
        "session_busy": data.session_busy,
        "last_success": data.last_success.isoformat(),
        **_status_diagnostics(data.status),
    }
    diagnostics["inventory"] = _inventory_diagnostics(data.inventory)
    diagnostics["raw"] = {
        "status": redact(data.status.raw),
        "inventory": redact(data.inventory.raw) if data.inventory else None,
    }
    diagnostics["extras"] = {
        "automatisms": [
            {
                "category": a.category,
                "commands": a.available_commands,
                "state": a.state,
                "position": a.position,
                "entity": entity_kind(a),
            }
            for a in data.automatisms
        ],
        "cameras": [{"type": c.type, "status": c.status} for c in data.cameras],
        "clip_count": len(data.clips),
        "latest_clip": _clip_summary(data),
        "failing_reads": sorted(getattr(coordinator, "_extras_failing", set())),
        "event_log": _event_log_summary(coordinator),
    }
    diagnostics["raw_api"] = await _raw_api(coordinator)
    return diagnostics


def _clip_summary(data: Any) -> dict[str, Any] | None:
    clip = data.latest_clip
    if clip is None:
        return None
    return {
        "taken_at": clip.taken_at.isoformat() if clip.taken_at else None,
        "kind": clip.kind,
        "category": clip.category,
        "format": clip.format,
    }


def _event_log_summary(coordinator: Any) -> dict[str, Any]:
    event_log = getattr(coordinator, "event_log", None)
    if event_log is None:
        return {"enabled": False}
    return {
        "enabled": True,
        "last_update_success": event_log.last_update_success,
        "entries": len(event_log.data or []),
    }


async def _raw_api(coordinator: Any) -> dict[str, Any]:
    """Every raw read, fetched now. Best effort: a failure is reported, never raised."""
    system = getattr(coordinator, "system", None)
    if system is None:
        return {"error": "no installation set up"}
    try:
        return await system.collect_raw(logbook_entries=5)  # type: ignore[no-any-return]
    except DaitemError as err:
        return {"error": f"{type(err).__name__}: {err}"}


def _update_interval_seconds(coordinator: Any) -> int | None:
    interval = getattr(coordinator, "update_interval", None)
    return int(interval.total_seconds()) if interval else None


def _arm_modes_discovered(coordinator: Any) -> bool | None:
    """Whether the panel answered the capability probe, rather than falling back to away."""
    system = getattr(coordinator, "system", None)
    capabilities = getattr(system, "capabilities", None)
    return getattr(capabilities, "discovered", None)


def _status_diagnostics(status: SystemStatus) -> dict[str, Any]:
    return {
        "panel_state": status.panel_state.value,
        "raw_state": status.state,
        "is_armed": status.is_armed,
        "is_arming": status.is_arming,
        "active_groups": status.active_groups,
        "command_status": status.command_status,
    }


def _inventory_diagnostics(inventory: Inventory | None) -> dict[str, Any] | None:
    """Device counts, types and faults, without the names that identify a home."""
    if inventory is None:
        return None

    return {
        "central_type": inventory.central_type,
        "central_serial": redact_identifier(inventory.central_serial),
        "has_io": inventory.has_io,
        "central_faults": sorted(fault.value for fault in inventory.central_anomalies.faults),
        "central_unknown_anomaly_keys": sorted(inventory.central_anomalies.unknown_keys),
        "sensor_count": len(inventory.sensors),
        "control_count": len(inventory.controls),
        "devices": [
            {
                "index": device.index,
                "kind": device.kind,
                "type": device.type,
                "group": device.group,
                "inhibited": device.inhibited,
                "faults": sorted(fault.value for fault in device.anomalies.faults),
                # The raw keys matter more than the mapped faults here: an anomaly key this
                # library does not know yet is exactly what a bug report needs to show.
                "anomaly_keys": sorted(device.anomalies.flags),
            }
            for device in inventory.devices
        ],
    }
