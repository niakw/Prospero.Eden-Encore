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

    # SAME game, different art AND resolution: source changed icon position
    # should still match a separately isolated Switch alpha sprite at its
    # normalized coordinates. Unlike exact pixels, this is ONLY a layout
    # candidate and cannot be used as an installed RomFS rectangle.
    other = Image.new("RGBA", (80, 64), (0, 0, 0, 0))
    ImageDraw.Draw(other).rectangle((20, 15, 39, 34), fill=(255, 0, 0, 255))
    altered = other.copy()
    ImageDraw.Draw(altered).rectangle((22, 17, 37, 32), fill=(5, 199, 210, 255))
    nx = Image.new("RGBA", (160, 128), (0, 0, 0, 0))
    ImageDraw.Draw(nx).ellipse((40, 30, 79, 69), fill=(20, 240, 30, 255))
    pc.write_bytes(png(other))
    pc_mod.write_bytes(png(altered))
    switch.write_bytes(png(nx))
    report = test.propose(pc, pc_mod, switch, "Synthetic Game", "Wii U", "gameplay")
    assert report["original_texture_comparison"] == "dimensions_differ"
    assert report["switch_candidate_rects_xywh"] is None
    layout = report["source_ui_layout_position_candidates"]
    assert len(layout) == 1, layout
    assert layout[0]["evidence"] == "same_game_layout_prior_only"
    assert layout[0]["symbol_identity_verified"] is False
    assert layout[0]["verified_switch_sprite_for_installation"] is False
    assert report["source_ui_layout_position_is_atlas_write_proof"] is False
    assert layout[0]["switch_alpha_sprite_candidate_xywh"] == [38, 28, 44, 44]

    # The same scene with a moved Nintendo icon must NOT be auto-linked
    # just because some texture changed on another platform.
    moved = Image.new("RGBA", (160, 128), (0, 0, 0, 0))
    ImageDraw.Draw(moved).ellipse((105, 80, 144, 119), fill=(20, 240, 30, 255))
    switch.write_bytes(png(moved))
    assert test.propose(pc, pc_mod, switch, "Synthetic Game", "Wii U", "gameplay")[
        "source_ui_layout_position_candidates"] == []

    # Multiple nearby alpha sprites are ambiguous and must not be guessed.
    ambiguous = Image.new("RGBA", (160, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ambiguous)
    draw.rectangle((47, 43, 58, 56), fill=(225, 0, 0, 255))
    draw.rectangle((63, 43, 74, 56), fill=(0, 225, 0, 255))
    switch.write_bytes(png(ambiguous))
    assert test.propose(pc, pc_mod, switch, "Synthetic Game", "Wii U", "gameplay")[
        "source_ui_layout_position_candidates"] == []

    # Restore the original equal-art fixture after the scaling/ambiguity
    # cases; otherwise the prior PC source is still 'other'.
    pc.write_bytes(png(original))
    pc_mod.write_bytes(png(original))
    switch.write_bytes(png(original))
    report = test.propose(pc, pc_mod, switch, "Synthetic Test", "PC", "menu")
    assert report["source_mod_pixel_differences"]["status"] == "pixel_identical"
    assert report["switch_candidate_rects_xywh"] is None

print("HOST FIXTURE PASS: exact art and layout-prior matching across different console resolutions")
print("Real game assets, cross-port correctness and PS5 firmware NOT tested")
