"""Translation assets.

`strings.json` is the source; `translations/en.json` must mirror it exactly and every
other language must cover the same keys. Both files are hand-maintained here, so nothing
but a test stops a new key from being added to one and forgotten in the others.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

INTEGRATION_DIR = Path("custom_components/daitem")
TRANSLATIONS_DIR = INTEGRATION_DIR / "translations"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _key_paths(value: Any, prefix: str = "") -> set[str]:
    """Every leaf path in a translation file, so a missing key names itself on failure."""
    if not isinstance(value, dict):
        return {prefix}
    return {path for key, item in value.items() for path in _key_paths(item, f"{prefix}.{key}" if prefix else key)}


def test_english_translation_mirrors_the_source_strings() -> None:
    assert _load(TRANSLATIONS_DIR / "en.json") == _load(INTEGRATION_DIR / "strings.json")


def test_every_language_covers_the_same_keys() -> None:
    expected = _key_paths(_load(INTEGRATION_DIR / "strings.json"))

    for path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        actual = _key_paths(_load(path))
        assert not expected - actual, f"{path.name} is missing {sorted(expected - actual)}"
        assert not actual - expected, f"{path.name} has unknown keys {sorted(actual - expected)}"


def test_placeholders_match_across_languages() -> None:
    """A translated string dropping `{installation_name}` would break device naming."""
    source = _load(INTEGRATION_DIR / "strings.json")
    expected = source["device"]["panel"]["name"]
    assert "{installation_name}" in expected

    for path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        translated = _load(path)["device"]["panel"]["name"]
        assert "{installation_name}" in translated, f"{path.name} dropped the placeholder"
