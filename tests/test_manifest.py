"""Manifest consistency.

Home Assistant installs the pinned pydaitem from PyPI, while CI develops against the
library from git. Nothing otherwise ties the two together, so a library change could ship
green here and fail at runtime for every user with a TypeError on an unknown argument.
This test is that missing link.
"""

from __future__ import annotations

import json
from pathlib import Path

import pydaitem

MANIFEST = Path(__file__).parent.parent / "custom_components" / "daitem" / "manifest.json"


def test_pinned_pydaitem_matches_the_library_in_use() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pins = [r for r in manifest["requirements"] if r.startswith("pydaitem")]
    assert len(pins) == 1, "expected exactly one pydaitem requirement"

    requirement = pins[0]
    assert "==" in requirement, f"pin pydaitem exactly, got {requirement!r}"

    pinned = requirement.split("==", 1)[1]
    assert pinned == pydaitem.__version__, (
        f"manifest pins pydaitem=={pinned} but the library in use is "
        f"{pydaitem.__version__}. Release the library first, then move the pin."
    )


def test_manifest_declares_what_hacs_and_hassfest_need() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key in ("domain", "name", "version", "documentation", "issue_tracker", "codeowners"):
        assert manifest.get(key), f"manifest is missing {key}"
    assert manifest["domain"] == "daitem"
