#!/usr/bin/env python3
"""Static verification of user-supplied, licensed DualSense art integration.

SOURCE inspection only. Does not compile, launch a GUI or run on PS5.
"""
from pathlib import Path
import re
import hashlib

ROOT = Path(__file__).resolve().parents[1]
ui = ROOT / "headless/prosperoeden/pe/ui"
asset = (ui / "dualsense_mask_asset.hpp").read_text()
texture = (ui / "textures.cpp").read_text()
widgets = (ui / "widgets.cpp").read_text()
about = (ui / "browse.cpp").read_text()
credit = (ROOT / "headless/prosperoeden/ui/art/PS5_ICONS_ATTRIBUTION.md").read_text()

assert "kDualSenseWidth = 144" in asset
assert "kDualSenseHeight = 100" in asset
assert "alpha quantized to 2-bit" in asset
assert "CC-BY-3.0" in asset
array = asset.split("kDualSenseAlphaRuns[] = {", 1)[1].split("};", 1)[0]
raw = bytes(int(n, 16) for n in re.findall(r"0x([a-fA-F0-9]{2})", array))
assert len(raw) == 1328
assert len(raw) % 2 == 0
assert hashlib.sha256(raw).hexdigest() == (
    "525f74a57a26b06d51b3dea9ccf361037bef04900567ff0aa3db5209171dee6f"
)
alpha = bytearray()
for count, level in zip(raw[::2], raw[1::2]):
    assert 1 <= count <= 255
    assert 0 <= level <= 3
    alpha.extend([level * 85] * count)
assert len(alpha) == 144 * 100
assert sum(bool(a) for a in alpha) > 500
assert alpha[0] == alpha[-1] == 0

assert '#include "pe/ui/dualsense_mask_asset.hpp"' in texture
assert "pad_image.rgba.resize(kPixels * 4u);" in texture
assert "level * 85u" in texture
assert "length > kPixels - pixel" in texture
assert "if (valid && pixel == kPixels)" in texture
assert 'load("art/controller.tga", &controller_)' in texture  # fallback
assert "c.textures.controller()" in widgets
assert "c.list.image(image, r, {0.0f, 0.0f, 1.0f, 1.0f}," in widgets
assert "Original vector fallback" in widgets
assert "controller_icon(c, r, lit);" in (ui / "home.cpp").read_text()
assert "dualsense_icon(c, {left - 2.0f" in (ui / "home.cpp").read_text()
assert "PS5 Button Icons and Controls" in credit
assert "Zacksly" in credit and "CC BY 3.0" in credit
assert "Modified" not in credit or "Changes made:" in credit
assert "DualSense icon: Zacksly (CC BY 3.0)" in about

print("SOURCE CONTRACT: licensed DualSense artwork, valid RLE, existing UI positions, About credit")
print("PS5 SDK compilation / visual capture / in-game graphic replacements: NOT TESTED")
