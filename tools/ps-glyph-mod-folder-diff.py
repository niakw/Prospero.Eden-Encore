#!/usr/bin/env python3
"""Offline, read-only diff of an *already extracted* community Switch UI mod.

Complements ps-glyph-mod-diff.py for .7z/.rar and non-ZIP layouts; does not
extract archives, execute installers, copy original resources or autoapprove
Nintendo-to-PlayStation semantics. Use only authorized local file trees.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, BASE / path)
    if spec is None or spec.loader is None:
        raise ValueError(f"missing local helper {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


diff = load("eden_ps_glyph_mod_diff", "ps-glyph-mod-diff.py")
pack = load("eden_ps_glyph_pack", "ps-glyph-pack.py")
MAX_ENTRIES = 16384
MAX_IMAGE_FILES = 128


def inventory_tree(mod_root: Path) -> list[Path]:
    if not mod_root.is_dir() or mod_root.is_symlink():
        raise ValueError("mod folder missing, symlink or not a directory")
    seen = set()
    files: list[Path] = []
    count = 0
    for current, directories, names in os.walk(mod_root, followlinks=False):
        current_path = Path(current)
        directories.sort()
        names.sort()
        for name in directories + names:
            candidate = current_path / name
            rel = candidate.relative_to(mod_root)
            pack._path(rel.as_posix())
            if candidate.is_symlink():
                raise ValueError(f"symlink forbidden: {rel}")
            key = rel.as_posix().casefold()
            if key in seen:
                raise ValueError("duplicate/case-colliding mod tree resource")
            seen.add(key)
            count += 1
            if count > MAX_ENTRIES:
                raise ValueError("mod folder has too many entries")
        for name in names:
            file = current_path / name
            if not file.is_file():
                raise ValueError("non-regular mod file")
            files.append(file)
    return files


def relative_romfs(path: Path) -> str | None:
    parts = path.parts
    for index, segment in enumerate(parts):
        if segment.lower() == "romfs":
            result = "/".join(parts[index + 1:])
            if result:
                pack._path(result)
                return result
            return None
    return None


def compare(mod_root: Path, original_romfs: Path) -> dict:
    if not original_romfs.is_dir() or original_romfs.is_symlink():
        raise ValueError("original RomFS folder missing or symlink")
    files = inventory_tree(mod_root)
    found = []
    attempted = 0
    for file in files:
        inside_mod = file.relative_to(mod_root)
        romfs_path = relative_romfs(inside_mod)
        if not romfs_path:
            continue
        result = {"mod_path": inside_mod.as_posix(), "romfs_path": romfs_path,
                  "original_sha256": None, "replacement_sha256": None,
                  "changed_rects_xywh": None}
        if file.suffix.lower() not in (".png", ".tga"):
            result["status"] = "proprietary_or_other_format_unexamined"
            found.append(result)
            continue
        if attempted >= MAX_IMAGE_FILES:
            result["status"] = "candidate_scan_limit"
            found.append(result)
            continue
        attempted += 1
        try:
            if file.stat().st_size > diff.MAX_IMAGE_BYTES:
                raise ValueError("replacement image exceeds size limit")
            original = pack._regular_file(original_romfs, pack._path(romfs_path))
            if original.stat().st_size > diff.MAX_IMAGE_BYTES:
                raise ValueError("original image exceeds size limit")
            with original.open("rb") as stream:
                original_bytes = stream.read(diff.MAX_IMAGE_BYTES + 1)
            with file.open("rb") as stream:
                mod_bytes = stream.read(diff.MAX_IMAGE_BYTES + 1)
            if (len(original_bytes) > diff.MAX_IMAGE_BYTES or
                    len(mod_bytes) > diff.MAX_IMAGE_BYTES):
                raise ValueError("image file exceeds size limit")
            result["original_sha256"] = hashlib.sha256(original_bytes).hexdigest()
            result["replacement_sha256"] = hashlib.sha256(mod_bytes).hexdigest()
            result.update(diff.image_diff(original_bytes, mod_bytes))
        except (OSError, ValueError, RuntimeError, diff.UnidentifiedImageError,
                diff.Image.DecompressionBombError) as error:
            result["status"] = "unverified_or_unsupported"
            result["reason"] = str(error)[:200]
        found.append(result)
    return {"schema": 1, "source_kind": "already_extracted_mod_folder",
            "source_dir_name": mod_root.name, "examined_image_count": attempted,
            "resources": found, "verified_title_update": None,
            "semantic_button_identity": None, "in_game_runtime_proof": None,
            "warning": "Geometry-only; no confirmed button mapping, no file extraction and no PS5 runtime test."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod-dir", type=Path, required=True)
    parser.add_argument("--original-romfs", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="optional NEW JSON output file")
    args = parser.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("unsafe output report path")
        text = json.dumps(compare(args.mod_dir, args.original_romfs), indent=2) + "\n"
        if args.out:
            args.out.write_text(text, encoding="utf-8")
            print(f"MOD FOLDER DIFF {args.out} (no files changed)")
        else:
            print(text, end="")
        return 0
    except (OSError, ValueError) as error:
        print(f"REJECTED mod folder diff: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
