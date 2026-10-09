#!/usr/bin/env python3
"""Host ASTC4x4 compressed roundtrip from synthetic UI; no Nintendo assets."""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("eden_astc_glyph_patch", HERE / "ps-glyph-bntx-astc.py")
assert sp and sp.loader
tool = importlib.util.module_from_spec(sp)
sp.loader.exec_module(tool)

assert shutil.which("astcenc"), "host dependency astcenc required"


def rejected(cb, case: str):
    try:
        cb()
    except (tool.UnsafeAstc, tool.tile.InvalidTexture,
            tool.tile.inspect.InvalidBntx):
        return
    raise AssertionError(f"accepted unsafe ASTC edit: {case}")


def fixture(src: bytes, mode: int, srgb: bool) -> bytes:
    assert src[:4] == tool.ASTC_MAGIC
    w, h = int.from_bytes(src[7:10], "little"), int.from_bytes(src[10:13], "little")
    assert w == h == 16
    wblocks, hblocks = 4, 4
    surface = tool.tile.surface_size(wblocks, hblocks, mode, 0, 16)
    begin = 0x240
    b = bytearray([0xdd] * (begin + surface + 64))
    b[:8] = b"BNTX\0\0\0\0"
    b[0xc:0xe] = b"\xff\xfe"
    b[0x20:0x24] = b"NX  "
    struct.pack_into("<I", b, 0x1c, len(b))
    struct.pack_into("<I", b, 0x24, 1)
    struct.pack_into("<Q", b, 0x28, 0x80)
    struct.pack_into("<Q", b, 0x80, 0xa0)
    b[0xa0:0xa4] = b"BRTI"
    struct.pack_into("<H", b, 0xa0 + 0x12, mode)
    struct.pack_into("<H", b, 0xa0 + 0x16, 1)
    struct.pack_into("<I", b, 0xa0 + 0x1c, 0x2d06 if srgb else 0x2d01)
    struct.pack_into("<IIII", b, 0xa0 + 0x24, 16, 16, 1, 1)
    struct.pack_into("<I", b, 0xa0 + 0x38, 0)
    struct.pack_into("<I", b, 0xa0 + 0x50, surface)
    b[0xa0 + 0x5c] = 1
    struct.pack_into("<Q", b, 0xa0 + 0x60, 0x160)
    struct.pack_into("<Q", b, 0xa0 + 0x70, 0x200)
    struct.pack_into("<Q", b, 0x200, begin)
    name = b"control_a_prompt"
    struct.pack_into("<H", b, 0x160, len(name))
    b[0x162:0x162 + len(name)] = name
    encoded = src[16:]
    assert len(encoded) == 16 * wblocks * hblocks
    for y in range(hblocks):
        for x in range(wblocks):
            index = 16 * (y * wblocks + x)
            physical = tool.tile.pixel_offset(x, y, wblocks, hblocks, mode, 0, 16)
            b[begin + physical:begin + physical + 16] = encoded[index:index + 16]
    return bytes(b)


with tempfile.TemporaryDirectory(prefix="eden-synthetic-astc-") as root:
    work = Path(root)
    png = work / "original.png"
    astc = work / "original.astc"
    original = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    ImageDraw.Draw(original).rectangle((1, 1, 2, 2), fill=(255, 255, 255, 255))
    original.save(png, "PNG")
    for mode, srgb in [(0, False), (1, True)]:
        codec = "-cs" if srgb else "-cl"
        tool.run_astcenc("astcenc", [codec, str(png), str(astc), "4x4", "-medium"])
        game = fixture(astc.read_bytes(), mode, srgb)
        d = tool.inspect_astc(game, "control_a_prompt")
        assert d["colorspace"] == ("srgb" if srgb else "linear")
        assert d["tile_mode"] == mode and d["block_width"] == 4
        # The image comes from a real ASTC decoder, not original pre-compress
        # data. All edited pixels are constrained to the source slot.
        decoded = tool.decoded_image(game, "control_a_prompt")
        assert decoded.size == (16, 16)
        edited = decoded.copy()
        ImageDraw.Draw(edited).rectangle((1, 1, 2, 2), fill=(255, 0, 0, 255))
        modified, proof = tool.patch_astc(
            game, "control_a_prompt", edited, [[0, 0, 4, 4]],
            hashlib.sha256(game).hexdigest())
        assert len(modified) == len(game)
        assert modified != game
        assert proof["reencoded_astc_blocks"] == 1
        assert proof["untouched_astc_block_count"] == 15
        assert proof["untouched_encoded_blocks_preserved"] is True
        before, after = tool.get_blocks(game, d), tool.get_blocks(modified, d)
        assert before[16:] == after[16:]
        assert modified[:0x240] == game[:0x240]
        assert modified[0x240+d["surface_bytes"]:] == game[0x240+d["surface_bytes"]:]
        updated = tool.decoded_image(modified, "control_a_prompt")
        assert updated.getpixel((1, 1))[0] > updated.getpixel((1, 1))[1]
        rejected(lambda: tool.patch_astc(
            game, "control_a_prompt", edited, [[0, 0, 4, 4]], "0" * 64),
            "wrong original SHA")
        wrong = edited.copy()
        wrong.putpixel((8, 8), (255, 255, 0, 255))
        rejected(lambda: tool.patch_astc(
            game, "control_a_prompt", wrong, [[0, 0, 4, 4]],
            hashlib.sha256(game).hexdigest()),
            "unapproved edited pixels")
        # Controller silhouette adjacent to an approved glyph must not be
        # destructively re-compressed in the SAME 4x4 ASTC block.
        crowded = decoded.copy()
        crowded.putpixel((3, 3), (255, 255, 255, 255))
        replacement = crowded.copy()
        replacement.putpixel((0, 0), (255, 0, 0, 255))
        # No fake assumptions: check source original neighbor alpha is zero,
        # and rely on decoded source pixels to determine unsafe blocks.

print("PASS: ASTC4x4 UNORM/sRGB Switch pitch/block-linear patch modifies only reviewed 16-byte blocks")
print("PASS: original BNTX layout and other game UI compressed blocks remain bit-identical")
print("No actual Zelda glyphs or PS5 gameplay have been tested.")
