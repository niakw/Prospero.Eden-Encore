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


def sarc_bytes(endian: str) -> bytes:
    blob = bytearray(0x58)
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
    w(0x2c, 8)
    blob[0x30:0x34] = b"SFNT"
    h(0x34, 8)
    blob[0x38:0x38 + len(name)] = name
    blob[0x38 + len(name)] = 0
    blob[0x50:0x58] = b"BNTX\0\0\0\0"
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
