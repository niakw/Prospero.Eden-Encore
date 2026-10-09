#!/usr/bin/env python3
"""Synthetic-only source fixture for conservative cross-platform sprite relocation.

No Nintendo textures or real game mods. Test file is intentionally NOT run
during the user's no-build/no-run gate.
"""
from __future__ import annotations

import importlib.util
import io
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "eden_exact_sprite_relocation", ROOT / "tools/ps-glyph-relocated-sprite.py")
assert spec and spec.loader
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def as_png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


with tempfile.TemporaryDirectory(prefix="eden-exact-sprite-relocation-") as work:
    root = Path(work)
    source = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
    patch = source.copy()
    d = ImageDraw.Draw(source)
    d.rectangle((4, 6, 14, 18), outline=(255, 50, 20, 255), width=2)
    patch.paste(source)
    d = ImageDraw.Draw(patch)
    d.rectangle((4, 6, 14, 18), outline=(20, 100, 255, 255), width=2)
    template = source.crop((1, 3, 18, 22))
    switch = Image.new("RGBA", (110, 70), (0, 0, 0, 0))
    # Parent atlases differ in size, offset and unrelated surrounding sprites.
    ImageDraw.Draw(switch).rectangle((2, 2, 9, 9), fill=(0, 255, 0, 255))
    switch.paste(template, (62, 31))
    sx, sm, nx = root / "pc-original.png", root / "pc-mod.png", root / "nx-original.png"
    sx.write_bytes(as_png(source))
    sm.write_bytes(as_png(patch))
    nx.write_bytes(as_png(switch))
    report = tool.propose(sx, sm, nx, [[1, 3, 17, 19]], "Synthetic Game", "PC", "menu")
    candidate = report["proposals"][0]
    assert candidate["status"] == "unique_exact_original_sprite", candidate
    assert candidate["switch_candidate_rect_xywh"] == [62, 31, 17, 19]
    assert candidate["semantic_mapping_verified"] is False
    assert report["ps5_runtime_verified"] is False

    # Changing RGB only in a completely transparent source slot is invisible.
    hidden = switch.copy()
    hidden.putpixel((62, 31), (80, 90, 100, 0))
    nx.write_bytes(as_png(hidden))
    assert tool.propose(sx, sm, nx, [[1, 3, 17, 19]], "Synthetic Game", "PC", "menu")[
        "proposals"][0]["status"] == "unique_exact_original_sprite"

    # A second full sprite clone is ambiguous; no coordinate may be selected.
    twice = switch.copy()
    twice.paste(template, (15, 35))
    nx.write_bytes(as_png(twice))
    result = tool.propose(sx, sm, nx, [[1, 3, 17, 19]], "Synthetic Game", "PC", "menu")
    assert result["proposals"][0]["status"] == "ambiguous_multiple_matches"
    assert result["proposals"][0]["switch_candidate_rect_xywh"] is None

    # One different source pixel on the Switch sprite breaks exact identity.
    different = switch.copy()
    different.putpixel((62 + 3, 31 + 3), (0, 0, 0, 255))
    nx.write_bytes(as_png(different))
    result = tool.propose(sx, sm, nx, [[1, 3, 17, 19]], "Synthetic Game", "PC", "menu")
    assert result["proposals"][0]["status"] == "no_exact_original_match"
    assert result["proposals"][0]["switch_candidate_rect_xywh"] is None

    # No actual change between PC original and mod must not generate a candidate.
    sm.write_bytes(as_png(source))
    nx.write_bytes(as_png(switch))
    result = tool.propose(sx, sm, nx, [[1, 3, 17, 19]], "Synthetic Game", "PC", "menu")
    assert result["proposals"][0]["status"] == "no_visible_mod_change"
    assert result["proposals"][0]["switch_candidate_rect_xywh"] is None

print("HOST FIXTURE PASS: unique moved sprite, invisible padding, ambiguous/recolored/no-op rejection")
print("NO native game assets, title-update verification or PS5 runtime testing")
