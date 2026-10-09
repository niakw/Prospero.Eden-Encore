#!/usr/bin/env python3
"""Offline same-size surgical BOTW Yaz0/SARC/BNTX glyph replacement archive.

Actual game-owned resources must be provided by their lawful holder:
  original Yaz0/SARC UI archive, BNTX member name, texture name, exact
  original hash, reviewed sprite XYWH and user-created RGBA edited PNG.
Never reads the console, extracts ROMs, redistributes game graphics, or
installs a mod automatically. The archive can be staged in a LayeredFS
mod only AFTER independent game/update and screenshot tests.

SARC table layout, section data offsets and other members are untouched.
Yaz0 is re-encoded as a valid, bounded, literal-only stream, not faked
by renaming a raw SARC to .sblarc. ASTC texture edits are block-preserving.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
MAX_ARCHIVE_OUT = 160 * 1024 * 1024


class UnsafeRepack(ValueError):
    pass


def ensure(cond: bool, message: str):
    if not cond:
        raise UnsafeRepack(message)


def load(name: str, file: str):
    sp = importlib.util.spec_from_file_location(name, HERE / file)
    ensure(sp is not None and sp.loader is not None, "missing offline helper")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


botw = load("eden_repack_yaz0", "ps-glyph-botw-yaz0.py")
astc = load("eden_repack_astc", "ps-glyph-bntx-astc.py")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def literal_yaz0(data: bytes) -> bytes:
    ensure(isinstance(data, bytes) and 0x20 <= len(data) <= botw.MAX_DECOMPRESSED,
           "only bounded SARC contents may be Yaz0-encoded")
    encoded_size = 16 + ((len(data) + 7) // 8) + len(data)
    ensure(encoded_size <= MAX_ARCHIVE_OUT, "lossless output exceeds Yaz0 guard")
    packed = bytearray(b"Yaz0" + len(data).to_bytes(4, "big") + bytes(8))
    for idx in range(0, len(data), 8):
        segment = data[idx:idx + 8]
        packed.append((0xff << (8 - len(segment))) & 0xff)
        packed.extend(segment)
    compressed = bytes(packed)
    ensure(len(compressed) == encoded_size and botw.decode(compressed) == data,
           "Yaz0 roundtrip failed")
    return compressed


def repack(source: bytes, member_name: str,
           modified_member: bytes) -> tuple[bytes, dict]:
    ensure(0x20 <= len(source) <= botw.MAX_INPUT and
           isinstance(member_name, str) and 0 < len(member_name) <= 240,
           "invalid input/source member")
    yaz0 = source[:4] == b"Yaz0"
    unpacked = botw.decode(source) if yaz0 else source
    description = botw.sarc.inventory_bytes(unpacked)
    matches = [m for m in description["members"] if m["name"] == member_name]
    ensure(len(matches) == 1 and member_name.endswith(".bntx"),
           "exact unique internal BNTX member required")
    item = matches[0]
    offset, length = item["content_offset"], item["content_bytes"]
    ensure(isinstance(modified_member, bytes) and len(modified_member) == length,
           "modification must preserve original SARC member size")
    original_member = unpacked[offset:offset + length]
    ensure(original_member.startswith(b"BNTX") and
           modified_member.startswith(b"BNTX") and
           original_member != modified_member, "not a changed BNTX member")
    replaced = bytearray(unpacked)
    replaced[offset:offset + length] = modified_member
    sarc_contents = bytes(replaced)
    updated = botw.sarc.inventory_bytes(sarc_contents)
    ensure(updated["member_count"] == description["member_count"] and
           [(x["name"], x["content_offset"], x["content_bytes"])
            for x in updated["members"]] ==
           [(x["name"], x["content_offset"], x["content_bytes"])
            for x in description["members"]],
           "SARC named member table or offsets changed")
    # Only the approved BNTX member data may differ. The SAME rebuilt SARC
    # byte length is required, so no offsets elsewhere can be displaced.
    ensure(unpacked[:offset] == sarc_contents[:offset] and
           unpacked[offset + length:] == sarc_contents[offset + length:] and
           len(unpacked) == len(sarc_contents), "non-target SARC bytes changed")
    result = literal_yaz0(sarc_contents) if yaz0 else sarc_contents
    ensure((botw.decode(result) if yaz0 else result) == sarc_contents,
           "final native UI archive failed exact roundtrip")
    return result, {
        "original_member_sha256": sha(original_member),
        "updated_member_sha256": sha(modified_member),
        "original_archive_sha256": sha(source),
        "updated_archive_sha256": sha(result),
        "compression": "Yaz0" if yaz0 else "plain SARC",
        "other_member_and_layout_bytes_preserved": True,
        "updated_member": member_name,
        "original_bytes": len(source), "updated_bytes": len(result),
        "uncompressed_sarc_bytes": len(sarc_contents),
    }


def build(archive: bytes, manifest: dict, edited: Image.Image,
          astcenc: str = "astcenc") -> tuple[bytes, dict]:
    ensure(manifest.get("schema") == 1 and
           manifest.get("original_archive_sha256") == sha(archive),
           "source original archive SHA-256 evidence mismatch")
    title = manifest.get("title_id")
    update = manifest.get("update_version")
    ensure(isinstance(title, str) and re.fullmatch(r"[0-9a-fA-F]{16}", title) and
           int(title, 16) != 0 and isinstance(update, str) and
           re.fullmatch(r"[0-9a-zA-Z_.+ -]{1,64}", update),
           "valid Switch Title ID and exact stated update version required")
    ensure(isinstance(manifest.get("scene"), str) and
           manifest["scene"] in ("menu", "gameplay", "hud", "controller_diagram",
                                  "world_interaction", "tutorial", "pause"),
           "source scene must be identified")
    name = manifest.get("member")
    texture = manifest.get("texture")
    ensure(isinstance(name, str) and isinstance(texture, str),
           "named original BNTX member and internal texture required")
    decoded = botw.decode(archive) if archive[:4] == b"Yaz0" else archive
    parsed = botw.sarc.inventory_bytes(decoded)
    matches = [m for m in parsed["members"] if m["name"] == name]
    ensure(len(matches) == 1, "target BNTX member missing or ambiguous")
    entry = matches[0]
    original_member = decoded[entry["content_offset"]:
                              entry["content_offset"] + entry["content_bytes"]]
    ensure(manifest.get("original_member_sha256") == sha(original_member),
           "original BNTX member fingerprint mismatch")
    updated_member, details = astc.patch_astc(
        original_member, texture, edited, manifest.get("rectangles"),
        manifest["original_member_sha256"], astcenc)
    result, evidence = repack(archive, name, updated_member)
    evidence["title_id"] = title.upper()
    evidence["user_declared_update_version"] = update
    evidence["scene"] = manifest["scene"]
    evidence["bntx_astc"] = details
    evidence["scene_verified_on_ps5"] = False
    evidence["game_version_cryptographically_verified"] = False
    evidence["layeredfs_mod_installed"] = False
    return result, evidence


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--edit-spec", type=Path, required=True,
                   help="reviewed JSON: schema/title/update/scene/archive+member SHA/member/texture/rectangles")
    p.add_argument("--edited-png", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--astcenc", default="astcenc")
    a = p.parse_args()
    try:
        ensure(a.original.is_file() and not a.original.is_symlink() and
               a.original.stat().st_size <= botw.MAX_INPUT,
               "original source missing or unsafe")
        ensure(a.edit_spec.is_file() and not a.edit_spec.is_symlink() and
               a.edit_spec.stat().st_size <= 128 * 1024,
               "reviewed edit plan missing or oversized")
        ensure(a.edited_png.is_file() and not a.edited_png.is_symlink() and
               a.edited_png.stat().st_size <= 64 * 1024 * 1024,
               "edited PNG missing or oversized")
        for target in (a.out, a.report):
            ensure(target.parent.is_dir() and not target.parent.is_symlink() and
                   not target.exists() and not target.is_symlink(),
                   "output or report already exists / has unsafe parent")
        manifest = json.loads(a.edit_spec.read_text("utf-8"))
        ensure(isinstance(manifest, dict), "edit evidence must be a JSON object")
        with Image.open(a.edited_png) as graphic:
            ensure(graphic.format == "PNG" and graphic.mode == "RGBA",
                   "original-same-size RGBA PNG input required")
            value, report = build(a.original.read_bytes(), manifest, graphic, a.astcenc)
        a.out.write_bytes(value)
        a.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"STAGED {a.out} (offline graphics candidate only; no runtime qualification)")
        return 0
    except (OSError, ValueError, botw.InvalidYaz0, botw.sarc.InvalidSarc,
            astc.UnsafeAstc, astc.tile.InvalidTexture) as exc:
        print(f"REJECTED BOTW UI patch: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
