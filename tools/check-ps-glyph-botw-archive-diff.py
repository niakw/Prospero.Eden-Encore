#!/usr/bin/env python3
"""Host-only synthetic BOTW original-vs-mod Yaz0/SARC/BNTX diff fixture."""
from __future__ import annotations

import importlib.util
import struct
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("eden_botw_archive_diff_test",
                                              HERE / "ps-glyph-botw-archive-diff.py")
assert spec and spec.loader
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def bntx_bytes(fill: int) -> bytes:
    blob = bytearray(0x300)
    blob[:8] = b"BNTX\0\0\0\0"
    blob[0x0c:0x0e] = b"\xff\xfe"
    blob[0x20:0x24] = b"NX  "
    struct.pack_into("<I", blob, 0x1c, len(blob))
    struct.pack_into("<I", blob, 0x24, 1)
    struct.pack_into("<Q", blob, 0x28, 0x80)
    struct.pack_into("<Q", blob, 0x80, 0xA0)
    blob[0xA0:0xA4] = b"BRTI"
    struct.pack_into("<H", blob, 0xA0 + 0x12, 1)  # pitch linear
    struct.pack_into("<H", blob, 0xA0 + 0x16, 1)
    struct.pack_into("<I", blob, 0xA0 + 0x1c, 0x0B01)
    struct.pack_into("<IIII", blob, 0xA0 + 0x24, 4, 4, 1, 1)
    struct.pack_into("<I", blob, 0xA0 + 0x50, 16)
    blob[0xA0 + 0x5c] = 1
    struct.pack_into("<Q", blob, 0xA0 + 0x60, 0x160)
    struct.pack_into("<Q", blob, 0xA0 + 0x70, 0x200)
    struct.pack_into("<Q", blob, 0x200, 0x240)
    name = b"ui_controller_prompt"
    struct.pack_into("<H", blob, 0x160, len(name))
    blob[0x162:0x162 + len(name)] = name
    blob[0x240:0x250] = bytes([fill] * 16)
    return bytes(blob)


def sarc(payload: bytes) -> bytes:
    name = b"__Combined.bntx"
    blob = bytearray(0x50 + len(payload))
    blob[:4] = b"SARC"
    blob[6:8] = b"\xff\xfe"
    struct.pack_into("<H", blob, 4, 0x14)
    struct.pack_into("<I", blob, 8, len(blob))
    struct.pack_into("<I", blob, 0xc, 0x50)
    struct.pack_into("<H", blob, 0x10, 0x100)
    blob[0x14:0x18] = b"SFAT"
    struct.pack_into("<H", blob, 0x18, 0x0c)
    struct.pack_into("<H", blob, 0x1a, 1)
    struct.pack_into("<I", blob, 0x1c, 101)
    name_hash = 0
    for ch in name:
        name_hash = (name_hash * 101 + ch) & 0xffffffff
    struct.pack_into("<I", blob, 0x20, name_hash)
    struct.pack_into("<I", blob, 0x24, 0x01000000)
    struct.pack_into("<I", blob, 0x2c, len(payload))
    blob[0x30:0x34] = b"SFNT"
    struct.pack_into("<H", blob, 0x34, 8)
    blob[0x38:0x38 + len(name)] = name
    blob[0x38 + len(name)] = 0
    blob[0x50:] = payload
    return bytes(blob)


def literal_yaz0(contents: bytes) -> bytes:
    result = bytearray(b"Yaz0" + len(contents).to_bytes(4, "big") + bytes(8))
    for start in range(0, len(contents), 8):
        segment = contents[start:start + 8]
        result.append((0xff << (8 - len(segment))) & 0xff)
        result.extend(segment)
    return bytes(result)


with tempfile.TemporaryDirectory(prefix="eden-botw-original-v-mod-") as folder:
    root = Path(folder)
    original = root / "original.sblarc"
    modded = root / "modded.sblarc"
    original.write_bytes(literal_yaz0(sarc(bntx_bytes(0x55))))
    modded.write_bytes(literal_yaz0(sarc(bntx_bytes(0xcc))))
    report = tool.compare(original, modded)
    assert report["original_member_count"] == 1
    assert report["mod_member_count"] == 1
    assert report["switch_glyph_positions_verified"] == 0
    assert len(report["changed_members"]) == 1
    item = report["changed_members"][0]
    assert item["name"] == "__Combined.bntx"
    assert item["status"] == "modified_member"
    assert item["reconstruction_ready"] is False
    assert item["pixel_rect_xywh"] is None
    changes = item["bntx"]
    assert changes["inspection"] == "bounded_encoded_data_comparison"
    assert changes["original_texture_count"] == 1
    assert len(changes["changed_or_unqualified_textures"]) == 1
    texture = changes["changed_or_unqualified_textures"][0]
    assert texture["name"] == "ui_controller_prompt"
    assert texture["difference"] == "encoded_image_changed"
    assert texture["pixel_rect_xywh"] is None
    assert texture["old_encoded_sha256"] != texture["mod_encoded_sha256"]
    # Identical members disappear from report; no invented mod difference.
    modded.write_bytes(original.read_bytes())
    assert not tool.compare(original, modded)["changed_members"]

    modded.write_bytes(literal_yaz0(sarc(bntx_bytes(0xcc))))
    corrupted = bytearray(modded.read_bytes())
    corrupted[4:8] = (tool.botw.MAX_DECOMPRESSED + 1).to_bytes(4, "big")
    modded.write_bytes(corrupted)
    try:
        tool.compare(original, modded)
    except tool.botw.InvalidYaz0:
        pass
    else:
        raise AssertionError("archive diff accepted decompression bomb")
    # Metadata-only changes must not invent altered decoded texture pixel
    # identities when the encoded first-mip image hash remains unchanged.
    metadata = bytearray(bntx_bytes(0x55))
    metadata[0xA0 + 0x34] = 7  # BRTI field not used by bounded image comparer
    assert tool.texture_changes(bntx_bytes(0x55), bytes(metadata))[
        "changed_or_unqualified_textures"] == []

print("PASS BOTW source-vs-mod SARC member and encoded BNTX texture fingerprint comparisons")
print("No game pixels, game archive output, PS5 UI patch, or copyright game assets generated.")
