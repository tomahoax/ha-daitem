"""Diagnostics download, meant to be safe to attach to a GitHub issue.

Everything here goes through `redaction`: the credentials and the refresh token never
appear, serial numbers and device names are kept only partially.

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
from pydaitem import Inventory, SystemStatus

from .const import CONF_SYSTEM_ID
from .coordinator import DaitemConfigEntry
from .redaction import partial, redact


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: DaitemConfigEntry) -> dict[str, Any]:
    """Return the redacted state of one installation."""
    # `runtime_data` is unset while an entry is still retrying its setup, which is exactly
    # when diagnostics are most likely to be requested. Degrade rather than raise.
    coordinator = getattr(entry, "runtime_data", None)
    data = getattr(coordinator, "data", None)

    diagnostics: dict[str, Any] = {
        "entry": {
            "title": partial(entry.title),
            "email": partial(str(entry.data.get(CONF_EMAIL, ""))),
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
    return diagnostics


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
        "central_serial": partial(inventory.central_serial),
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
