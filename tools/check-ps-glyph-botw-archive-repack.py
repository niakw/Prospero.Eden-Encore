#!/usr/bin/env python3
"""Synthetic SARC/Yaz0 surgical member repacking; no game archive or mod."""
from __future__ import annotations

import hashlib
import importlib.util
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location(
    "eden_repack_bridge", HERE / "ps-glyph-botw-archive-repack.py")
assert sp and sp.loader
repack = importlib.util.module_from_spec(sp)
sp.loader.exec_module(repack)


def rejected(cb, reason: str):
    try:
        cb()
    except (repack.UnsafeRepack, repack.botw.InvalidYaz0,
            repack.botw.sarc.InvalidSarc):
        return
    raise AssertionError("accepted invalid repack: " + reason)


def sarc_two_members() -> bytes:
    names = ["__Combined.bntx", "MainLayout.bflyt"]
    data = {
        "__Combined.bntx": b"BNTX\0\0\0\0" + bytes(range(112)),
        "MainLayout.bflyt": b"FLYT" + bytes(range(30)),
    }
    # SARC SFAT table must be sorted by game-native multiplier hash.
    keys = sorted(names, key=lambda x: glyph_hash(x))
    text = bytearray()
    name_positions = {}
    for name in keys:
        name_positions[name] = len(text) // 4
        raw = name.encode() + b"\x00"
        text.extend(raw)
        while len(text) % 4:
            text.append(0)
    sfat_begin = 0x14
    sfnt = sfat_begin + 0x0c + len(keys) * 16
    names_begin = sfnt + 8
    data_offset = ((names_begin + len(text) + 15) // 16) * 16
    combined = bytearray()
    pointers = {}
    for name in keys:
        pointers[name] = (len(combined), len(combined) + len(data[name]))
        combined.extend(data[name])
    blob = bytearray(data_offset + len(combined))
    blob[:4] = b"SARC"
    blob[6:8] = b"\xff\xfe"
    struct.pack_into("<H", blob, 4, 0x14)
    struct.pack_into("<I", blob, 8, len(blob))
    struct.pack_into("<I", blob, 0xc, data_offset)
    struct.pack_into("<H", blob, 0x10, 0x100)
    blob[sfat_begin:sfat_begin + 4] = b"SFAT"
    struct.pack_into("<H", blob, sfat_begin + 4, 12)
    struct.pack_into("<H", blob, sfat_begin + 6, len(keys))
    struct.pack_into("<I", blob, sfat_begin + 8, 101)
    for i, name in enumerate(keys):
        pos = sfat_begin + 12 + i * 16
        start, end = pointers[name]
        struct.pack_into("<IIII", blob, pos,
                         glyph_hash(name),
                         0x01000000 | name_positions[name], start, end)
    blob[sfnt:sfnt+4] = b"SFNT"
    struct.pack_into("<H", blob, sfnt + 4, 8)
    blob[names_begin:names_begin + len(text)] = text
    blob[data_offset:] = combined
    return bytes(blob)


def glyph_hash(name: str) -> int:
    result = 0
    for value in name.encode():
        result = (result * 101 + value) & 0xffffffff
    return result


plain = sarc_two_members()
inv = repack.botw.sarc.inventory_bytes(plain)
assert inv["member_count"] == 2
assert {item["name"] for item in inv["members"]} == {
    "__Combined.bntx", "MainLayout.bflyt"}
target = next(item for item in inv["members"]
              if item["name"] == "__Combined.bntx")
old_member = plain[target["content_offset"]:
                   target["content_offset"] + target["content_bytes"]]
patched_member = bytearray(old_member)
patched_member[43:48] = b"\xfa\xfb\xfc\xfd\xfe"
patched_member = bytes(patched_member)

for sample in (plain, repack.literal_yaz0(plain)):
    output, receipt = repack.repack(sample, "__Combined.bntx", patched_member)
    assert receipt["other_member_and_layout_bytes_preserved"] is True
    assert receipt["updated_member_sha256"] == hashlib.sha256(patched_member).hexdigest()
    assert receipt["compression"] == ("Yaz0" if sample[:4] == b"Yaz0" else "plain SARC")
    unpacked = repack.botw.decode(output) if output[:4] == b"Yaz0" else output
    assert unpacked[:target["content_offset"]] == plain[:target["content_offset"]]
    assert unpacked[target["content_offset"] + target["content_bytes"]:] == (
        plain[target["content_offset"] + target["content_bytes"]:])
    assert repack.botw.sarc.inventory_bytes(unpacked)["member_count"] == 2
    assert unpacked[target["content_offset"]:
                    target["content_offset"] + target["content_bytes"]] == patched_member
    rejected(lambda: repack.repack(sample, "__Combined.bntx", b"WRONG"),
             "source member resized")
    rejected(lambda: repack.repack(sample, "Other.bntx", patched_member),
             "different member name")
    rejected(lambda: repack.repack(sample, "__Combined.bntx", old_member),
             "no changed data")
    rejected(lambda: repack.repack(sample, "MainLayout.bflyt", patched_member),
             "non-BNTX member")

result = repack.literal_yaz0(plain)
assert result.startswith(b"Yaz0")
assert repack.botw.decode(result) == plain
assert result != plain
rejected(lambda: repack.literal_yaz0(b"too short"), "bad SARC data")

print("PASS: whole BOTW SARC/Yaz0 roundtrip, exact-sized changed BNTX and other archive members intact")
print("PASS: source member sizes, cases, archive table, extra files and unsafe edits rejected")
print("Synthetic fixture only; no Nintendo ROMFS, console file, or installable glyph mod produced")
