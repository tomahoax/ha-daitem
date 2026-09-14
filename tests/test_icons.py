"""Icons and names of every entity that carries a translation key.

Fault keys are `Fault.value`, which also composes the entity's unique id. A fault renamed
on the pydaitem side would therefore silently produce a nameless, iconless entity rather
than an error, so the mapping is pinned here from both ends.

The rules below deliberately mirror what hassfest enforces in CI, so a mistake fails in a
second locally instead of a minute later on a runner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydaitem import Fault

from custom_components.daitem.binary_sensor import CENTRAL_FAULTS, DETECTOR_FAULTS
from custom_components.daitem.sensor import FIRMWARES

COMPONENT = Path(__file__).parent.parent / "custom_components" / "daitem"

#: The union of both dicts: `tamper_mechanical` and `tamper_wired` are reported by the
#: panel and by detectors alike, and share a single key on purpose.
FAULT_KEYS = sorted({fault.value for fault in (*CENTRAL_FAULTS, *DETECTOR_FAULTS)})

#: Inhibition is not a fault, but it is a binary sensor and needs the same treatment.
BINARY_SENSOR_KEYS = sorted([*FAULT_KEYS, "inhibited"])

SENSOR_KEYS = sorted([*(d.key for d in FIRMWARES), "group"])

#: Which platforms declare which keys, so a new one cannot be added to the code without
#: reaching the translation and icon files.
EXPECTED = {"binary_sensor": BINARY_SENSOR_KEYS, "sensor": SENSOR_KEYS}


def _load(name: str) -> dict[str, Any]:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def icons() -> dict[str, Any]:
    return _load("icons.json")["entity"]


@pytest.fixture(scope="module")
def names() -> dict[str, Any]:
    return _load("strings.json")["entity"]


@pytest.mark.parametrize(("platform", "keys"), EXPECTED.items())
def test_every_entity_has_an_icon_and_a_name(
    platform: str, keys: list[str], icons: dict[str, Any], names: dict[str, Any]
) -> None:
    assert sorted(icons[platform]) == keys
    assert sorted(names[platform]) == keys


@pytest.mark.parametrize("key", BINARY_SENSOR_KEYS)
def test_a_binary_sensor_icon_changes_with_its_state(key: str, icons: dict[str, Any]) -> None:
    """A distinct icon per entity must not cost the raised/clear signal the device class gave.

    `default` covers the healthy state, `state.on` the raised one. hassfest rejects the two
    being equal, which would mean the condition is no longer visible at a glance.
    """
    entry = icons["binary_sensor"][key]
    assert entry["state"]["on"] != entry["default"]


def test_icons_are_material_design_names(icons: dict[str, Any]) -> None:
    for platform in EXPECTED:
        for key, entry in icons[platform].items():
            values = [entry["default"], *entry.get("state", {}).values()]
            assert all(v.startswith("mdi:") for v in values), f"{platform}.{key}"


def test_the_fault_keys_are_the_library_fault_values() -> None:
    """Guards the coupling this file exists for, from the other end."""
    assert set(FAULT_KEYS) <= {fault.value for fault in Fault}
