#!/usr/bin/env python3
"""Synthetic ONLY cross-platform glyph transfer fixtures; no real game assets.

Run only during an authorized testing phase. Never implies PC art works in
Eden Encore or verifies game title/update/container compatibility.
"""
from __future__ import annotations

import importlib.util
import io
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
MODULE = importlib.util.spec_from_file_location(
    "eden_cross_platform_image",
    ROOT / "tools/ps-glyph-cross-platform-image.py")
assert MODULE and MODULE.loader
test = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(test)


def png(img: Image.Image) -> bytes:
    result = io.BytesIO()
    img.save(result, format="PNG")
    return result.getvalue()


with tempfile.TemporaryDirectory(prefix="eden-cross-platform-glyph-") as temp:
    root = Path(temp)
    pc = root / "pc-original.png"
    pc_mod = root / "pc-modified.png"
    switch = root / "switch-original.png"
    original = Image.new("RGBA", (48, 32), (0, 0, 0, 0))
    ImageDraw.Draw(original).rectangle((4, 4, 11, 11), fill=(255, 0, 0, 255))
    modified = original.copy()
    ImageDraw.Draw(modified).rectangle((4, 4, 11, 11), fill=(255, 255, 0, 255))
    pc.write_bytes(png(original))
    pc_mod.write_bytes(png(modified))
    switch.write_bytes(png(original))
    report = test.propose(pc, pc_mod, switch, "Synthetic Test", "PC", "menu")
    assert report["original_texture_comparison"] == "rendered_pixels_identical"
    assert report["switch_candidate_rects_xywh"] == [[4, 4, 8, 8]]
    assert report["candidate_is_installed_or_semantically_approved"] is False
    assert report["switch_game_update_verified"] is False

    # Invisible RGB differences under alpha zero cannot affect visible glyph.
    transparent = original.copy()
    transparent.putpixel((0, 0), (34, 190, 200, 0))
    switch.write_bytes(png(transparent))
    report = test.propose(pc, pc_mod, switch, "Synthetic Test", "PC", "menu")
    assert report["original_texture_comparison"] == "rendered_pixels_identical"
    # RGB differences at alpha=1 are real and must NOT be suppressed by
    # 8-bit premultiply rounding (prior implementation missed this case).
    semi = original.copy()
    semi.putpixel((4, 4), (254, 0, 0, 1))
    switch.write_bytes(png(semi))
    report = test.propose(pc, pc_mod, switch, "Synthetic Test", "PC", "menu")
    assert report["original_texture_comparison"] == "visible_pixels_differ"
    assert report["switch_candidate_rects_xywh"] is None
    switch.write_bytes(png(original))

    # One genuinely different source icon means no coordinate transfer.
    different = original.copy()
    different.putpixel((0, 0), (255, 255, 255, 255))
    switch.write_bytes(png(different))
    report = test.propose(pc, pc_mod, switch, "Synthetic Test", "PC", "menu")
    assert report["original_texture_comparison"] == "visible_pixels_differ"
    assert report["switch_candidate_rects_xywh"] is None

    switch.write_bytes(png(Image.new("RGBA", (96, 64))))
    report = test.propose(pc, pc_mod, switch, "Synthetic Test", "PC", "menu")
    assert report["original_texture_comparison"] == "dimensions_differ"
    assert report["switch_candidate_rects_xywh"] is None

    pc_mod.write_bytes(png(original))
    switch.write_bytes(png(original))
    report = test.propose(pc, pc_mod, switch, "Synthetic Test", "PC", "menu")
    assert report["source_mod_pixel_differences"]["status"] == "pixel_identical"
    assert report["switch_candidate_rects_xywh"] is None

print("HOST FIXTURE PASS: exact rendered image match, transparent RGB tolerance, no guesses on mismatches")
print("Real game assets, cross-port correctness and PS5 firmware NOT tested")
