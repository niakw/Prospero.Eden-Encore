#!/usr/bin/env python3
"""Diff read-only BOTW Switch original/mod Yaz0/SARC and embedded BNTX textures.

This is a forensic SOURCE-IDENTIFICATION tool, not an image generator.
For byte-hashed matching SARC member names, it identifies which members
actually changed. For BNTX/NX members with compatible metadata and bounded
image ranges, it can identify which NAMED encoded textures differ.
BNTX/ASTC data is not decoded; no pixel rectangles or button identities
are inferred. Only previously authorized local originals/mods are read.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_REPORT_ITEMS = 4096


class UnsafeArchive(ValueError):
    pass


def require(yes: bool, reason: str) -> None:
    if not yes:
        raise UnsafeArchive(reason)


def helper(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    require(spec is not None and spec.loader is not None, "missing helper " + filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


botw = helper("eden_archive_diff_botw", "ps-glyph-botw-yaz0.py")
bntx = helper("eden_archive_diff_bntx", "ps-glyph-bntx-inspect.py")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_archive(path: Path) -> tuple[bytes, bytes, dict]:
    require(path.is_file() and not path.is_symlink(), "invalid or linked game archive")
    require(0x20 <= path.stat().st_size <= botw.MAX_INPUT, "archive too large")
    original = path.read_bytes()
    require(0x20 <= len(original) <= botw.MAX_INPUT, "truncated original archive read")
    contents = botw.decode(original) if original[:4] == b"Yaz0" else original
    parsed = botw.sarc.inventory_bytes(contents)
    return original, contents, parsed


def member_data(content: bytes, member: dict) -> bytes:
    offset = member["content_offset"]
    length = member["content_bytes"]
    require(0 <= offset <= len(content) and 0 <= length <= len(content) - offset,
            "member pointer outside validated SARC")
    return content[offset:offset + length]


def mip_digest(blob: bytes, texture: dict) -> str | None:
    # The BRTI's reported encoded_image_bytes covers encoded image data,
    # not necessarily a decoded 2D sprite or single mip level. This
    # fingerprint distinguishes altered BYTES, not pixel glyph positions.
    starts = texture["mip_data_offsets"]
    length = texture["encoded_image_bytes"]
    if not isinstance(starts, list) or not starts or not isinstance(length, int):
        return None
    first = starts[0]
    if not isinstance(first, int) or first < 0 or length <= 0 or length > len(blob) - first:
        return None
    return sha(blob[first:first + length])


def texture_changes(original: bytes, modified: bytes) -> dict:
    try:
        a, b = bntx.inspect(original), bntx.inspect(modified)
    except (bntx.InvalidBntx, ValueError, OSError) as exc:
        return {"inspection": "unsupported_or_invalid_bntx", "reason": str(exc)[:120]}
    names_a = [x["name"] for x in a["textures"]]
    names_b = [x["name"] for x in b["textures"]]
    require(len(names_a) == len(set(x.casefold() for x in names_a)) and
            len(names_b) == len(set(x.casefold() for x in names_b)),
            "ambiguous duplicate BNTX texture names")
    aa = {x["name"].casefold(): x for x in a["textures"]}
    bb = {x["name"].casefold(): x for x in b["textures"]}
    names = sorted(set(aa) | set(bb))
    updated = []
    for key in names:
        first, second = aa.get(key), bb.get(key)
        if first is None or second is None:
            updated.append({"name": (first or second)["name"],
                            "difference": "added_or_removed_texture",
                            "pixel_rect_xywh": None})
            continue
        descriptor = ("width", "height", "format_code", "tile_mode", "mip_count",
                      "array_length", "depth", "dimension", "encoded_image_bytes")
        compatibility = all(first.get(k) == second.get(k) for k in descriptor)
        first_sha = mip_digest(original, first)
        second_sha = mip_digest(modified, second)
        if not compatibility or first_sha is None or second_sha is None:
            updated.append({"name": second["name"],
                            "difference": "incompatible_or_unbounded_texture",
                            "old_format": first["format"],
                            "new_format": second["format"],
                            "pixel_rect_xywh": None})
            continue
        if first_sha != second_sha:
            updated.append({"name": second["name"], "difference": "encoded_image_changed",
                            "format": second["format"], "width": second["width"],
                            "height": second["height"], "tile_mode": second["tile_mode"],
                            "old_encoded_sha256": first_sha,
                            "mod_encoded_sha256": second_sha,
                            "pixel_rect_xywh": None})
    return {
        "inspection": "bounded_encoded_data_comparison",
        "original_texture_count": len(aa),
        "mod_texture_count": len(bb),
        "changed_or_unqualified_textures": updated,
        "warning": ("Encoded image hashes do NOT indicate changed pixel XYWH "
                    "or that any specific texture is shown as a button in the game."),
    }


def compare(original_path: Path, mod_path: Path) -> dict:
    raw_a, decoded_a, src = load_archive(original_path)
    raw_b, decoded_b, mod = load_archive(mod_path)
    require(src["hash_multiplier"] == mod["hash_multiplier"],
            "original and mod SARC name-hash schemes differ")
    aa = {item["name"].casefold(): item for item in src["members"] if item["name"]}
    bb = {item["name"].casefold(): item for item in mod["members"] if item["name"]}
    require(len(aa) == sum(bool(x["name"]) for x in src["members"]) and
            len(bb) == sum(bool(x["name"]) for x in mod["members"]),
            "duplicate member names")
    changes = []
    for key in sorted(set(aa) | set(bb)):
        a, b = aa.get(key), bb.get(key)
        if a is None or b is None:
            changes.append({"name": (a or b)["name"],
                            "status": "added_or_removed_member",
                            "reconstruction_ready": False})
            continue
        initial = member_data(decoded_a, a)
        replacement = member_data(decoded_b, b)
        if initial == replacement:
            continue
        item = {"name": b["name"], "status": "modified_member",
                "original_sha256": sha(initial),
                "mod_sha256": sha(replacement),
                "original_bytes": len(initial),
                "mod_bytes": len(replacement),
                "reconstruction_ready": False,
                "pixel_rect_xywh": None}
        if b["name"].lower().endswith(".bntx"):
            item["bntx"] = texture_changes(initial, replacement)
        changes.append(item)
        require(len(changes) <= MAX_REPORT_ITEMS, "too many changed SARC members")
    return {
        "schema": 1,
        "original_archive": original_path.name,
        "mod_archive": mod_path.name,
        "original_archive_sha256": sha(raw_a),
        "mod_archive_sha256": sha(raw_b),
        "original_sarc_sha256": sha(decoded_a),
        "mod_sarc_sha256": sha(decoded_b),
        "original_member_count": len(src["members"]),
        "mod_member_count": len(mod["members"]),
        "changed_members": changes,
        "unidentified_original_members": sum(x["name"] is None for x in src["members"]),
        "unidentified_mod_members": sum(x["name"] is None for x in mod["members"]),
        "switch_glyph_positions_verified": 0,
        "warning": ("Only byte-identical source/member matches are omitted. "
                    "Mod BNTX changes may contain unrelated textures; this "
                    "never redistributes game assets or certifies PlayStation glyphs."),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original", type=Path, required=True, help="authorized original BOTW Switch UI SARC/Yaz0")
    p.add_argument("--modded", type=Path, required=True, help="authorized modded UI SARC/Yaz0")
    p.add_argument("--out", type=Path, help="NEW JSON report file; never overwrite")
    opts = p.parse_args()
    try:
        if opts.out and (opts.out.exists() or opts.out.is_symlink() or
                         not opts.out.parent.is_dir() or opts.out.parent.is_symlink()):
            raise UnsafeArchive("unsafe or existing output")
        value = json.dumps(compare(opts.original, opts.modded),
                           ensure_ascii=False, indent=2) + "\n"
        if opts.out:
            opts.out.write_text(value, encoding="utf-8")
            print(f"BOTW UI BYTE DIFFERENCES {opts.out} (not an active PS5 patch)")
        else:
            print(value, end="")
        return 0
    except (UnsafeArchive, botw.InvalidYaz0, botw.sarc.InvalidSarc,
            bntx.InvalidBntx, ValueError, OSError) as exc:
        print(f"REJECTED BOTW UI comparison: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
