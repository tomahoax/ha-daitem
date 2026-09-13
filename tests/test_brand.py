"""Brand assets served to HACS and to the Home Assistant frontend.

Since Home Assistant 2026.3, `brand/` inside the integration overrides the CDN with no
manifest change, and HACS refuses to list an integration whose `brand/icon.png` is missing.
So a renamed or resized file here breaks the listing rather than just looking wrong, which
is worth catching before a release rather than in the HACS job.

The dark variants matter because the logo is black ink on transparency: without them it is
all but invisible on Home Assistant's dark theme.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

BRAND = Path(__file__).parent.parent / "custom_components" / "daitem" / "brand"

EXPECTED_SIZES = {
    "icon.png": (256, 256),
    "icon@2x.png": (512, 512),
    "dark_icon.png": (256, 256),
    "dark_icon@2x.png": (512, 512),
}


def _png_header(path: Path) -> tuple[int, int, int]:
    """Return width, height and PNG colour type, straight from the IHDR chunk."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height, data[25]


@pytest.mark.parametrize(("filename", "size"), EXPECTED_SIZES.items())
def test_brand_asset_is_a_png_of_the_expected_size(filename: str, size: tuple[int, int]) -> None:
    path = BRAND / filename
    assert path.is_file(), f"{filename} is missing; HACS and the frontend both read this directory"

    width, height, colour_type = _png_header(path)
    assert (width, height) == size
    # Colour type 6 is RGBA: the background has to stay transparent, on either theme.
    assert colour_type == 6, f"{filename} has no alpha channel"
