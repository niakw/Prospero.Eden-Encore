#!/usr/bin/env python3
"""Host-only Tegra RGBA8 image codec tests, zero Nintendo game assets used."""
from __future__ import annotations

import hashlib
import importlib.util
import struct

from PIL import Image

HERE = __import__("pathlib").Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("eden_bntx_rgba", HERE / "ps-glyph-bntx-rgba.py")
assert spec and spec.loader
codec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codec)


def invalid(callback, case: str):
    try:
        callback()
    except (codec.InvalidTexture, codec.inspect.InvalidBntx):
        return
    raise AssertionError("accepted invalid BNTX fixture: " + case)


def bntx_fixture(w: int, h: int, mode: int, bh: int = 0) -> bytes:
    surface = codec.surface_size(w, h, mode, bh)
    begin = 0x240
    b = bytearray([0xcc] * (begin + surface + 64))
    b[:8] = b"BNTX\x00\x00\x00\x00"
    b[0x0c:0x0e] = b"\xff\xfe"
    b[0x20:0x24] = b"NX  "
    struct.pack_into("<I", b, 0x1c, len(b))
    struct.pack_into("<I", b, 0x24, 1)
    struct.pack_into("<Q", b, 0x28, 0x80)
    struct.pack_into("<Q", b, 0x80, 0xa0)
    b[0xa0:0xa4] = b"BRTI"
    struct.pack_into("<H", b, 0xa0 + 0x12, mode)
    struct.pack_into("<H", b, 0xa0 + 0x16, 1)
    struct.pack_into("<I", b, 0xa0 + 0x1c, 0x0b01)
    struct.pack_into("<IIII", b, 0xa0 + 0x24, w, h, 1, 1)
    struct.pack_into("<I", b, 0xa0 + 0x38, bh)
    struct.pack_into("<I", b, 0xa0 + 0x50, surface)
    b[0xa0 + 0x5c] = 1
    struct.pack_into("<Q", b, 0xa0 + 0x60, 0x160)
    struct.pack_into("<Q", b, 0xa0 + 0x70, 0x200)
    struct.pack_into("<Q", b, 0x200, begin)
    name = b"controller_buttons"
    struct.pack_into("<H", b, 0x160, len(name))
    b[0x162:0x162 + len(name)] = name
    return bytes(b)


for w, h, mode, bh in [
    (4, 4, 1, 0),
    (9, 17, 1, 0),
    (31, 17, 0, 0),
    (13, 9, 0, 1),
    (21, 27, 0, 2),
    (39, 41, 0, 3),
]:
    original = bntx_fixture(w, h, mode, bh)
    desc = codec.describe(original, "controller_buttons")
    assert desc["width"] == w and desc["height"] == h
    assert desc["surface_bytes"] == codec.surface_size(w, h, mode, bh)
    png = Image.new("RGBA", (w, h))
    png.putdata([((x * 17) % 256, (y * 23) % 256, (x ^ y) % 256, 255)
                 for y in range(h) for x in range(w)])
    expected = hashlib.sha256(original).hexdigest()
    updated = codec.encode_rgba(original, "controller_buttons", png, expected)
    assert len(updated) == len(original)
    assert codec.decode_rgba(updated, "controller_buttons").tobytes() == png.tobytes()
    # Complete BNTX wrapper, headers, pointers and padding must be unchanged.
    d = desc["data_offset"]
    end = d + desc["surface_bytes"]
    assert updated[:d] == original[:d]
    assert updated[end:] == original[end:]
    assert updated != original
    assert codec.encode_rgba(updated, "controller_buttons", png,
                             hashlib.sha256(updated).hexdigest()) == updated
    invalid(lambda: codec.encode_rgba(original, "controller_buttons", png,
                                      "f" * 64), "wrong source hash")
    invalid(lambda: codec.encode_rgba(original, "controller_buttons",
                                      Image.new("RGBA", (w + 1, h)), expected),
            "different dimensions")

bad = bytearray(bntx_fixture(8, 8, 0, 0))
struct.pack_into("<I", bad, 0xa0 + 0x1c, 0x2d01)
invalid(lambda: codec.describe(bytes(bad), "controller_buttons"), "ASTC treated as RGBA8")
bad = bytearray(bntx_fixture(8, 8, 0, 0))
struct.pack_into("<H", bad, 0xa0 + 0x16, 2)
invalid(lambda: codec.describe(bytes(bad), "controller_buttons"), "multi-mip")
bad = bytearray(bntx_fixture(8, 8, 0, 0))
struct.pack_into("<I", bad, 0xa0 + 0x38, 6)
invalid(lambda: codec.describe(bytes(bad), "controller_buttons"), "invalid block height")
bad = bytearray(bntx_fixture(8, 8, 0, 0))
struct.pack_into("<Q", bad, 0x200, len(bad) - 8)
invalid(lambda: codec.describe(bytes(bad), "controller_buttons"), "image pointer overflow")
bad = bytearray(bntx_fixture(8, 8, 1, 0))
struct.pack_into("<I", bad, 0xa0 + 0x50, 4)
invalid(lambda: codec.describe(bytes(bad), "controller_buttons"), "encoded span too small")
bad = bytearray(bntx_fixture(8, 8, 0, 0))
struct.pack_into("<I", bad, 0xa0 + 0x38, 0x7)
invalid(lambda: codec.describe(bytes(bad), "controller_buttons"), "block height illegal")
bad = bytearray(bntx_fixture(8, 8, 0, 0))
struct.pack_into("<I", bad, 0xa0 + 0x2c, 2)
invalid(lambda: codec.describe(bytes(bad), "controller_buttons"), "array texture")
bad = bntx_fixture(8, 8, 0, 0)
invalid(lambda: codec.describe(bad, "not_present"), "missing named texture")

# For an entire 64-byte GOB, offsets for all 16 4-byte pixels x 8 rows
# must be unique: this catches nibble/stripe bugs that naive roundtrips
# with the SAME incorrect address calculator might miss.
addrs = [codec.pixel_offset(x, y, 16, 8, 0, 0)
         for y in range(8) for x in range(16)]
assert sorted(addrs) == list(range(0, 512, 4))
# Known Tegra X1 GOB stripe mapping:
assert codec.pixel_offset(0, 0, 16, 8, 0, 0) == 0
assert codec.pixel_offset(4, 0, 16, 8, 0, 0) == 32
assert codec.pixel_offset(8, 0, 16, 8, 0, 0) == 256
assert codec.pixel_offset(0, 1, 16, 8, 0, 0) == 16
assert codec.pixel_offset(0, 2, 16, 8, 0, 0) == 64
assert codec.pixel_offset(0, 4, 16, 8, 0, 0) == 128

print("PASS BNTX RGBA8: exact non-square pitch/block-linear decode, re-encode and Tegra GOB mapping")
print("PASS: original BNTX metadata/padding stay bit-identical, wrong hashes/mips/ASTC/arrays rejected")
print("Host synthetic fixtures only, no real BOTW ASTC renderer, repack or PS5 qualification")
