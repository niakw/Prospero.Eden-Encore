#!/usr/bin/env python3
"""Host-only BOTW Yaz0 -> SARC -> embedded BNTX chain regression tests."""
from __future__ import annotations

import importlib.util
import struct
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tools"
sp = importlib.util.spec_from_file_location("eden_yaz0_bounded", ROOT / "ps-glyph-botw-yaz0.py")
assert sp and sp.loader
yaz = importlib.util.module_from_spec(sp)
sp.loader.exec_module(yaz)


def rejects(code, reason):
    try:
        code()
    except (yaz.InvalidYaz0, yaz.sarc.InvalidSarc):
        return
    raise AssertionError(f"accepted {reason}")


def sarc_bytes():
    payload = b"BNTX\0\0\0\0"
    blob = bytearray(0x50 + len(payload))
    blob[:4] = b"SARC"
    blob[6:8] = b"\xff\xfe"
    struct.pack_into("<H", blob, 4, 0x14)
    struct.pack_into("<I", blob, 8, len(blob))
    struct.pack_into("<I", blob, 12, 0x50)
    struct.pack_into("<H", blob, 0x10, 0x100)
    blob[0x14:0x18] = b"SFAT"
    struct.pack_into("<H", blob, 0x18, 12)
    struct.pack_into("<H", blob, 0x1a, 1)
    struct.pack_into("<I", blob, 0x1c, 101)
    name = b"__Combined.bntx"
    code = 0
    for b in name:
        code = ((code * 101) + b) & 0xffffffff
    struct.pack_into("<I", blob, 0x20, code)
    struct.pack_into("<I", blob, 0x24, 0x01000000)
    struct.pack_into("<I", blob, 0x28, 0)
    struct.pack_into("<I", blob, 0x2c, len(payload))
    blob[0x30:0x34] = b"SFNT"
    struct.pack_into("<H", blob, 0x34, 8)
    blob[0x38:0x38 + len(name)] = name
    blob[0x38 + len(name)] = 0
    blob[0x50:] = payload
    return bytes(blob)


def literal_yaz0(data: bytes) -> bytes:
    head = b"Yaz0" + len(data).to_bytes(4, "big") + bytes(8)
    compressed = bytearray()
    for i in range(0, len(data), 8):
        run = data[i:i + 8]
        compressed.append((0xff << (8 - len(run))) & 0xff)
        compressed.extend(run)
    return head + compressed


raw = sarc_bytes()
yaz0 = literal_yaz0(raw)
assert yaz.decode(yaz0) == raw
assert yaz.decode(yaz0 + bytes(8)) == raw
assert yaz.sarc.inventory_bytes(yaz.decode(yaz0))["members"][0]["name"] == "__Combined.bntx"
# Overlapping LZ77 match must reuse newly produced bytes correctly.
repeat = b"Yaz0" + (48).to_bytes(4, "big") + bytes(8) + b"\x80A\x00\x00\x1d"
assert yaz.decode(repeat) == b"A" * 48

rejects(lambda: yaz.decode(yaz0[:-3]), "truncated literal stream")
rejects(lambda: yaz.decode(yaz0 + b"nonpadding"), "nonzero trailing output data")
rejects(lambda: yaz.decode(yaz0[:8] + b"NONZERO!" + yaz0[16:]),
        "nonzero reserved bytes")
rejects(lambda: yaz.decode(yaz0[:4] + (yaz.MAX_DECOMPRESSED + 1).to_bytes(4, "big") +
                           yaz0[8:]), "decompression bomb")
rejects(lambda: yaz.decode(b"Yaz0" + (48).to_bytes(4, "big") + bytes(8) +
                           b"\x00\x00\x00"), "copy before start")
rejects(lambda: yaz.decode(b"Yaz0" + (48).to_bytes(4, "big") + bytes(8) +
                           b"\x80A\x00\x00\xff"), "copy past declared size")
rejects(lambda: yaz.decode(b"Yaz0" + (48).to_bytes(4, "big") + bytes(8) +
                           b"\x80A\x00\x00"), "truncated backref length")

with tempfile.TemporaryDirectory(prefix="eden-botw-yaz0-test-") as tmp:
    source = Path(tmp) / "Common.sblarc"
    source.write_bytes(yaz0)
    report = yaz.inventory(source, nested=True)
    assert report["compression"] == "Yaz0"
    assert report["sarc"]["member_count"] == 1
    assert report["sarc"]["members"][0]["name"] == "__Combined.bntx"
    assert report["bntx_chain"]["embedded_bntx_candidates"][0]["status"] == "nested_bntx_unreadable"
    assert report["sprite_pixel_rectangles"] is None
    assert report["ps5_art_qualified"] is False
    source.write_bytes(raw)
    report = yaz.inventory(source, nested=False)
    assert report["compression"] == "uncompressed"
    assert report["sarc"]["member_count"] == 1
    assert "bntx_chain" not in report

print("PASS BOTW Yaz0/SARC: bounded lossless literals/backrefs, SARC metadata, nested BNTX fail-closed")
print("No Nintendo proprietary source was downloaded, written or installed.")
