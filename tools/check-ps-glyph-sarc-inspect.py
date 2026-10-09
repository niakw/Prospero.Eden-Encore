#!/usr/bin/env python3
"""Synthetic read-only SARC v0x100 regression; run only in authorized test phase."""
from __future__ import annotations

import importlib.util
import struct
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("eden_sarc_inspector", ROOT / "tools/ps-glyph-sarc-inspect.py")
assert spec and spec.loader
sarc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sarc)


def sarc_bytes(endian: str, payload: bytes = b"BNTX\0\0\0\0") -> bytes:
    blob = bytearray(0x50 + len(payload))
    blob[:4] = b"SARC"
    blob[6:8] = b"\xff\xfe" if endian == "<" else b"\xfe\xff"

    def h(pos: int, value: int):
        struct.pack_into(endian + "H", blob, pos, value)

    def w(pos: int, value: int):
        struct.pack_into(endian + "I", blob, pos, value)

    h(0x04, 0x14)
    w(0x08, len(blob))
    w(0x0c, 0x50)
    h(0x10, 0x100)
    blob[0x14:0x18] = b"SFAT"
    h(0x18, 0x0c)
    h(0x1a, 1)
    w(0x1c, 101)
    name = b"__Combined.bntx"
    hashed = 0
    for byte in name:
        hashed = (hashed * 101 + byte) & 0xffffffff
    w(0x20, hashed)
    w(0x24, 0x01000000)
    w(0x28, 0)
    w(0x2c, len(payload))
    blob[0x30:0x34] = b"SFNT"
    h(0x34, 8)
    blob[0x38:0x38 + len(name)] = name
    blob[0x38 + len(name)] = 0
    blob[0x50:0x50 + len(payload)] = payload
    return bytes(blob)


with tempfile.TemporaryDirectory(prefix="eden-glyph-sarc-fixture-") as work:
    p = Path(work) / "Common.blarc"
    for endian in ("<", ">"):
        p.write_bytes(sarc_bytes(endian))
        result = sarc.inventory(p)
        assert result["member_count"] == 1
        assert result["members"][0]["name"] == "__Combined.bntx"
        assert result["members"][0]["content_offset"] == 0x50
        assert result["members"][0]["content_bytes"] == 8
        assert result["members"][0]["ui_candidate"] is False
        assert result["members"][0]["magic"] == b"BNTX\0\0\0\0".hex()
    # Nested BNTX resource with one named UI texture, no real game bytes.
    inner = bytearray(0x300)
    inner[:8] = b"BNTX\0\0\0\0"
    inner[0x0C:0x0E] = b"\xff\xfe"
    inner[0x20:0x24] = b"NX  "
    struct.pack_into("<I", inner, 0x1C, len(inner))
    struct.pack_into("<I", inner, 0x24, 1)
    struct.pack_into("<Q", inner, 0x28, 0x80)
    struct.pack_into("<Q", inner, 0x80, 0xA0)
    inner[0xA0:0xA4] = b"BRTI"
    struct.pack_into("<H", inner, 0xA0 + 0x12, 1)
    struct.pack_into("<H", inner, 0xA0 + 0x16, 1)
    struct.pack_into("<I", inner, 0xA0 + 0x1C, 0x0B01)
    struct.pack_into("<IIII", inner, 0xA0 + 0x24, 64, 64, 1, 1)
    struct.pack_into("<I", inner, 0xA0 + 0x50, 128)
    inner[0xA0 + 0x5C] = 1
    struct.pack_into("<Q", inner, 0xA0 + 0x60, 0x160)
    struct.pack_into("<Q", inner, 0xA0 + 0x70, 0x200)
    struct.pack_into("<Q", inner, 0x200, 0x240)
    name = b"controller_button_icons"
    struct.pack_into("<H", inner, 0x160, len(name))
    inner[0x162:0x162+len(name)] = name
    p.write_bytes(sarc_bytes("<", bytes(inner)))
    chain_spec = importlib.util.spec_from_file_location(
        "eden_sarc_bntx_chain", ROOT / "tools/ps-glyph-sarc-bntx-chain.py")
    assert chain_spec and chain_spec.loader
    chain_mod = importlib.util.module_from_spec(chain_spec)
    chain_spec.loader.exec_module(chain_mod)
    chain = chain_mod.inspect_chain(p)
    assert chain["embedded_bntx_candidates"][0]["status"] == "byte_offsets_inspected_only"
    tex = chain["embedded_bntx_candidates"][0]["textures"][0]
    assert tex["name"] == "controller_button_icons"
    assert tex["sarc_brti_byte_offset"] == 0x50 + 0xA0
    assert tex["sarc_mip_data_byte_offsets"] == [0x50 + 0x240]
    assert chain["image_pixel_coordinates"] is None
    wrong = bytearray(sarc_bytes("<"))
    struct.pack_into("<I", wrong, 0x08, 0xffffffff)
    p.write_bytes(wrong)
    try:
        sarc.inventory(p)
    except sarc.InvalidSarc:
        pass
    else:
        raise AssertionError("accepted declared SARC file-size overflow")
    wrong = bytearray(sarc_bytes("<"))
    struct.pack_into("<I", wrong, 0x2c, 0xffffffff)
    p.write_bytes(wrong)
    try:
        sarc.inventory(p)
    except sarc.InvalidSarc:
        pass
    else:
        raise AssertionError("accepted SARC member out of bounds")
    p.write_bytes(b"\x28\xb5\x2f\xfd" + b"compressed")
    try:
        sarc.inventory(p)
    except sarc.InvalidSarc:
        pass
    else:
        raise AssertionError("accepted ZSTD compressed bytes as plain SARC")

print("HOST FIXTURE PASS: little/big endian SARC member byte offsets and rejection guards")
print("No real Nintendo archive or console test was performed")
