"""Identifiers of the devices the integration registers, in one place.

Each one is both the device registry identifier and the key its entities are tracked by
(`entity.async_track_new`), so building it twice in two ways would let the two drift.
"""

from __future__ import annotations

from pydaitem import Automatism, Camera, Device


def device_key(system_id: int, device: Device) -> str:
    """Identity of one inventory device, unique across every family.

    `Device.index` is numbered per list, not globally: on a live installation the detectors
    run 1 to 9 and the controls 1 to 4, so the index alone collides. Including `kind`
    separates them, and for a detector it reproduces exactly the identifiers already in the
    registry, so nothing existing is renumbered.
    """
    return f"{system_id}_{device.kind}_{device.index}"


def automation_key(system_id: int, automatism: Automatism) -> str:
    return f"{system_id}_automatism_{automatism.id}"


def camera_key(system_id: int, camera: Camera) -> str:
    return f"{system_id}_camera_{camera.id}"
