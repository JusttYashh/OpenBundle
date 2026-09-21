"""Rasterize the top of docs/demo.svg so PyPI can show a PNG (no SVG)."""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "docs" / "demo.svg"
OUT = ROOT / "docs" / "demo.png"
MAX_Y = 980
SCALE = 2


def main() -> None:
    svg = SVG.read_text(encoding="utf-8")
    spans = [
        (int(x), int(y), fill, unescape(text))
        for x, y, fill, text in re.findall(
            r'<tspan x="(\d+)" y="(\d+)" fill="([^"]+)">(.*?)</tspan>',
            svg,
        )
        if int(y) <= MAX_Y
    ]
    for candidate in ("consola.ttf", "Consolas.ttf", "C:/Windows/Fonts/consola.ttf"):
        try:
            font = ImageFont.truetype(candidate, 22)
            break
        except OSError:
            font = None
    else:
        font = ImageFont.load_default()
    width = 920 * SCALE
    height = (max(y for _, y, _, _ in spans) + 28) * SCALE
    img = Image.new("RGB", (width, height), "#0d1117")
    draw = ImageDraw.Draw(img)
    for x, y, fill, text in spans:
        draw.text((x * SCALE, (y - 16) * SCALE), text, fill=fill, font=font)
    img.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} {img.size} {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
