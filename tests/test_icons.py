"""Icons and names of the fault sensors.

Both are keyed on `Fault.value`, which also composes the entity's unique id. A fault
renamed on the pydaitem side would therefore silently produce a nameless, iconless entity
rather than an error, so the mapping is pinned here.

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

COMPONENT = Path(__file__).parent.parent / "custom_components" / "daitem"

#: The union of both dicts: `tamper_mechanical` and `tamper_wired` are reported by the
#: panel and by detectors alike, and share a single key on purpose.
FAULT_KEYS = sorted({fault.value for fault in (*CENTRAL_FAULTS, *DETECTOR_FAULTS)})


def _load(name: str) -> dict[str, Any]:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def icons() -> dict[str, Any]:
    return _load("icons.json")["entity"]["binary_sensor"]


@pytest.fixture(scope="module")
def names() -> dict[str, Any]:
    return _load("strings.json")["entity"]["binary_sensor"]


def test_every_fault_sensor_has_an_icon_and_a_name(icons: dict[str, Any], names: dict[str, Any]) -> None:
    assert sorted(icons) == FAULT_KEYS
    assert sorted(names) == FAULT_KEYS


@pytest.mark.parametrize("key", FAULT_KEYS)
def test_the_icon_changes_when_the_fault_is_raised(key: str, icons: dict[str, Any]) -> None:
    """A distinct icon per fault must not cost the raised/clear signal the device class gave.

    `default` covers the healthy state, `state.on` the raised one. hassfest rejects the two
    being equal, which would mean the fault is no longer visible at a glance.
    """
    entry = icons[key]
    raised = entry["state"]["on"]
    assert raised != entry["default"]


@pytest.mark.parametrize("key", FAULT_KEYS)
def test_icons_are_material_design_names(key: str, icons: dict[str, Any]) -> None:
    entry = icons[key]
    for value in (entry["default"], *entry["state"].values()):
        assert value.startswith("mdi:")


def test_the_keys_are_the_library_fault_values() -> None:
    """Guards the coupling this file exists for, from the other end."""
    assert set(FAULT_KEYS) <= {fault.value for fault in Fault}
