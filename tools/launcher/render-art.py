#!/usr/bin/env python3
# ProsperoEden - Launcher art from the source images (run by tools/launcher/assets.sh).
# Copyright (C) 2026 BlackBearReloaded
# SPDX-License-Identifier: GPL-3.0-or-later
"""Writes the Prospero.Eden Encore launcher's baked art.

  brand.tga       Prospero.Eden Encore logo, for the header and games without cover art.
  controller.tga  a controller in white on transparent, tinted by the home screen.

The old ProsperoEden scenic backdrop is intentionally no longer generated or loaded.
render-art.py [name...] renders only the named pictures (brand, controller).
"""

import sys

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "headless/prosperoeden/ui/art"


def save_tga(image, name):
    image.convert("RGBA").save(ART / name, orientation=1)
    print(f"{name}: {image.size[0]}x{image.size[1]}")


def controller():
    """The controller as a mask: the shell is opaque, its touchpad, sticks and buttons are holes.

    Drawn in a 72x50 box (the size on screen) at 16 times that, then reduced to 144x100.
    """
    k = 16
    mask = Image.new("L", (72 * k, 50 * k), 0)
    draw = ImageDraw.Draw(mask)

    def box(x0, y0, x1, y1, radius, fill):
        draw.rounded_rectangle((x0 * k, y0 * k, x1 * k, y1 * k), radius * k, fill=fill)

    def disc(x, y, radius, fill):
        draw.ellipse(((x - radius) * k, (y - radius) * k, (x + radius) * k, (y + radius) * k), fill=fill)

    def bar(x0, y0, x1, y1, width, fill):
        draw.line((x0 * k, y0 * k, x1 * k, y1 * k), fill=fill, width=round(width * k))
        disc(x0, y0, width / 2, fill)
        disc(x1, y1, width / 2, fill)

    # The shell: a wide body and two grips that lean outwards.
    box(3.5, 5, 68.5, 34.5, 13, 255)
    bar(15.5, 25, 10, 40.5, 13.5, 255)
    bar(56.5, 25, 62, 40.5, 13.5, 255)
    # Touchpad, with the two small buttons beside it.
    box(25, 8.5, 47, 20.5, 3.2, 0)
    bar(21.6, 9.6, 21.2, 12.6, 1.5, 0)
    bar(50.4, 9.6, 50.8, 12.6, 1.5, 0)
    # Direction pad and the four buttons.
    box(9.2, 15.4, 18.2, 18.2, 1.2, 0)
    box(12.3, 12.3, 15.1, 21.3, 1.2, 0)
    for dx, dy in ((0, -3.7), (3.7, 0), (0, 3.7), (-3.7, 0)):
        disc(58.3 + dx, 16.8 + dy, 1.55, 0)
    # Sticks (a ring around a cap) and the round button between them.
    for x in (26.2, 45.8):
        disc(x, 27.6, 4.7, 0)
        disc(x, 27.6, 2.9, 255)
    disc(36, 27.4, 1.5, 0)
    mask = mask.resize((144, 100), Image.Resampling.LANCZOS)
    icon = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    icon.putalpha(mask)
    return icon


def main():
    ART.mkdir(parents=True, exist_ok=True)
    wanted = set(sys.argv[1:]) or {"brand", "controller"}
    unknown = wanted - {"brand", "controller"}
    if unknown:
        raise SystemExit("unknown Encore launcher art: " + ", ".join(sorted(unknown)))
    if "brand" in wanted:
        source = ROOT / "assets/icon0.png"
        icon = Image.open(source).convert("RGBA")
        icon = icon.resize((384, 384), Image.Resampling.LANCZOS)
        save_tga(icon, "brand.tga")
    if "controller" in wanted:
        save_tga(controller(), "controller.tga")


if __name__ == "__main__":
    main()
