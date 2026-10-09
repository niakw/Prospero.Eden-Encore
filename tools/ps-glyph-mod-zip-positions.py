#!/usr/bin/env python3
"""Inspect real Switch controller-UI mod ZIP files for original-game glyph positions.

A game mod supplies complete changed resources. Discover every archive
under RomFS, check matching original Switch files and compare decoded
ASTC texture pixels in-memory, WITHOUT unpacking mod graphics or
redistributing someone else's replacement sprites. Report all changed
native UI textures and verified isolated original sprite positions.

For unsupported non-SARC formats report the exact names requiring
specialist parsers rather than claiming zero changes/game compatibility.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
MAX_ARCHIVES = 96
MAX_ENTRY_BYTES = 128 * 1024 * 1024
ALLOWED = {".sblarc", ".ssarc", ".sarc", ".blarc"}


def helper(name: str, path: str):
    sp = importlib.util.spec_from_file_location(name, TOOLS / path)
    if not sp or not sp.loader:
        raise ValueError("missing required offline parser " + path)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return mod


positions = helper("eden_zip_glyph_pixel_positions", "ps-glyph-botw-mod-texture-positions.py")
inventory = helper("eden_zip_glyph_inventory", "ps-glyph-mod-inventory.py")
pack = helper("eden_zip_glyph_paths", "ps-glyph-pack.py")


def gather(mod_zip: Path, original_romfs: Path, scene: str,
           astcenc: str = "astcenc") -> dict:
    report = inventory.inventory(mod_zip)
    if not original_romfs.is_dir() or original_romfs.is_symlink():
        raise ValueError("original matching RomFS folder absent or symlink")
    inspected, unresolved = [], []
    selected = [x for x in report["files"] if x.get("romfs_path")]
    # A real UI mod can contain hundreds of layouts, icons and language
    # files, even if only a few are ASTC SARC archives. Bound the expensive
    # decoded scans, not the total number of ZIP entries.
    archive_budget = MAX_ARCHIVES
    seen = set()
    with zipfile.ZipFile(mod_zip) as z:
        for member in selected:
            relative = member["romfs_path"]
            key = relative.casefold()
            if key in seen:
                raise ValueError("duplicate RomFS path in mod ZIP")
            seen.add(key)
            if member["extension"] not in ALLOWED:
                unresolved.append({"romfs_path": relative,
                                   "status": "different_resource_format_not_ignored",
                                   "format": member["extension"]})
                continue
            if archive_budget <= 0:
                unresolved.append({"romfs_path": relative,
                                   "status": "bounded_native_ui_scan_budget_exhausted"})
                continue
            archive_budget -= 1
            if member["uncompressed_bytes"] > MAX_ENTRY_BYTES:
                unresolved.append({"romfs_path": relative,
                                   "status": "large_archive_skipped"})
                continue
            try:
                path = pack._path(relative)
                source = pack._regular_file(original_romfs, path)
                if source.stat().st_size > MAX_ENTRY_BYTES:
                    raise ValueError("original source archive over limit")
                original = source.read_bytes()
                with z.open(member["archive_path"]) as input_file:
                    changed = input_file.read(MAX_ENTRY_BYTES + 1)
                if len(changed) > MAX_ENTRY_BYTES:
                    raise ValueError("ZIP entry exceeded decompressed byte cap")
                evidence = positions.evidence_bytes(original, changed, scene, astcenc)
                inspected.append({
                    "romfs_path": relative,
                    "original_file_sha256": hashlib.sha256(original).hexdigest(),
                    "mod_file_sha256": hashlib.sha256(changed).hexdigest(),
                    "mod_archive_member": member["archive_path"],
                    "positions": evidence,
                })
            except (OSError, ValueError, zipfile.BadZipFile,
                    positions.archive.UnsafeArchive,
                    positions.archive.botw.InvalidYaz0,
                    positions.archive.botw.sarc.InvalidSarc) as exc:
                unresolved.append({"romfs_path": relative, "status": "unmatched_or_unreadable",
                                   "reason": str(exc)[:180]})
    return {
        "schema": 1,
        "source_mod_zip": mod_zip.name,
        "source_mod_sha256": report["archive_sha256"],
        "scanned_romfs_entries": len(selected),
        "matched_native_ui_archives": len(inspected),
        "glyph_position_candidates": sum(x["positions"]["ui_sprite_position_proposals"]
                                         for x in inspected),
        "matched_archives": inspected,
        "unresolved": unresolved,
        "mod_binaries_redistributed": False,
        "original_game_bytes_redistributed": False,
        "all_candidate_action_labels_unreviewed": True,
        "hardware_installation_qualified": False,
        "warning": ("Game mods expose real changed resource paths and pixels. "
                    "No false assumption that every archive uses Yaz0/SARC "
                    "or that every changed texture is a controller glyph."),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mod-zip", type=Path, required=True)
    p.add_argument("--original-romfs", type=Path, required=True)
    p.add_argument("--scene", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--astcenc", default="astcenc")
    a = p.parse_args()
    try:
        if a.out.exists() or a.out.is_symlink() or not a.out.parent.is_dir() or (
            a.out.parent.is_symlink()
        ):
            raise ValueError("report must be a new file in an ordinary parent")
        result = gather(a.mod_zip, a.original_romfs, a.scene, a.astcenc)
        a.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print("SWITCH MOD UI POSITIONS:",
              result["glyph_position_candidates"], "verified original sprite locations;",
              len(result["unresolved"]), "unresolved resources")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print("REJECTED SWITCH MOD ZIP:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
