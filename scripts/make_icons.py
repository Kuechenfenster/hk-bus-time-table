#!/usr/bin/env python3
"""Generate the brand icons used by the Marketplace listing.

Renders the Material Design Icons "bus" glyph (Apache-2.0 license), recolored,
to custom_components/hk_bus_timetable/brand/ as PNG at the sizes the
Marketplace / brands conventions expect.

The SVG glyph is rasterized with macOS QuickLook (qlmanage) at 1024px; the
render is used as an alpha mask over a solid color fill, which yields correct
anti-aliased transparency.

Requires: macOS (qlmanage) and Pillow (`pip install pillow`).
Usage (from the repository root):
    python3 scripts/make_icons.py
"""

from __future__ import annotations

import pathlib
import subprocess
import tempfile

from PIL import Image

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BRAND_DIR = REPO_ROOT / "custom_components" / "hk_bus_timetable" / "brand"

# mdi:bus from https://pictogrammers.com/library/mdi/icon/bus/ (Apache-2.0)
BUS_PATH = (
    "M4,16C4,16.88 4.39,17.67 5,18.22V20A1,1 0 0,0 6,21H7A1,1 0 0,0 8,20V19H16V20"
    "A1,1 0 0,0 17,21H18A1,1 0 0,0 19,20V18.22C19.61,17.67 20,16.88 20,16V6"
    "C20,2.5 16.42,2 12,2C7.58,2 4,2.5 4,6V16"
    "M7.5,17A1.5,1.5 0 0,1 6,15.5A1.5,1.5 0 0,1 7.5,14A1.5,1.5 0 0,1 9,15.5"
    "A1.5,1.5 0 0,1 7.5,17"
    "M16.5,17A1.5,1.5 0 0,1 15,15.5A1.5,1.5 0 0,1 16.5,14A1.5,1.5 0 0,1 18,15.5"
    "A1.5,1.5 0 0,1 16.5,17"
    "M18,11H6V6H18V11Z"
)
BUS_COLOR = "#E53935"  # KMB-red; readable on light and dark HA themes

SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 -2 28 28">
  <path d="{path}" fill="#000000" fill-rule="nonzero" stroke="none"/>
</svg>"""

RENDER_SIZE = 1024
ICON_SIZES = [(256, "icon.png"), (512, "icon@2x.png")]


def render_mask(size: int) -> Image.Image:
    """Rasterize the bus glyph (black on white) and return it as an alpha mask."""
    svg = SVG_TEMPLATE.format(path=BUS_PATH)
    with tempfile.TemporaryDirectory() as tmp:
        svg_path = pathlib.Path(tmp) / "bus.svg"
        svg_path.write_text(svg, encoding="utf-8")
        subprocess.run(
            ["qlmanage", "-t", "-s", str(RENDER_SIZE), "-o", tmp, str(svg_path)],
            check=True,
            capture_output=True,
        )
        rendered = Image.open(f"{svg_path}.png")
        # Flatten onto white, then invert: glyph (black) -> opaque alpha.
        flat = Image.new("RGB", rendered.size, "white")
        if rendered.mode == "RGBA":
            flat.paste(rendered, mask=rendered.getchannel("A"))
        else:
            flat.paste(rendered.convert("RGB"))
        mask = flat.convert("L").point(lambda value: 255 - value)
        return mask.resize((size, size), Image.LANCZOS)


def render_icon(size: int, dest: pathlib.Path) -> None:
    image = Image.new("RGBA", (size, size), BUS_COLOR)
    image.putalpha(render_mask(size))
    image.save(dest)
    print(f"wrote {dest.relative_to(REPO_ROOT)} ({image.width}x{image.height})")


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    for size, filename in ICON_SIZES:
        render_icon(size, BRAND_DIR / filename)


if __name__ == "__main__":
    main()
