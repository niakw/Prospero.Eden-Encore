#!/usr/bin/env python3
"""Reuse known PlayStation atlas coordinates across titles/versions by SHA-256.

An EXACT original resource byte-for-byte match is required. Different title
IDs/update versions still need human approval that control semantics match;
the default output deliberately leaves every PS button unassigned (null).
--approve-same-semantics opts in to carrying over previously verified labels.
No game assets are copied, patched, uploaded or installed by this tool.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / "tools/ps-glyph-atlas.py"
MODULE = importlib.util.spec_from_file_location("eden_ps_glyph_atlas", SOURCE)
if MODULE is None or MODULE.loader is None:
    raise SystemExit("missing ps-glyph-atlas.py")
atlas = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(atlas)


def load_spec(path: Path) -> dict:
    atlas.require(path.is_file() and not path.is_symlink() and
                  path.stat().st_size <= atlas.MAX_SPEC, "unsafe/oversized source spec")
    doc = json.loads(path.read_text("utf-8"), object_pairs_hook=atlas.nondup)
    atlas.require(isinstance(doc, dict) and set(doc) ==
                  {"schema", "title_id", "update_version", "variant", "atlases"} and
                  type(doc["schema"]) is int and doc["schema"] == 1 and
                  isinstance(doc["title_id"], str) and
                  atlas.HEX16.fullmatch(doc["title_id"]) is not None and
                  isinstance(doc["update_version"], str) and
                  atlas.VERSION.fullmatch(doc["update_version"]) is not None and
                  doc["variant"] in atlas.VARIANTS and
                  isinstance(doc["atlases"], list) and 0 < len(doc["atlases"]) <= 64,
                  "invalid known graphic atlas spec")
    seen = set()
    for entry in doc["atlases"]:
        atlas.require(isinstance(entry, dict) and set(entry) ==
                      {"romfs_path", "original_sha256", "slots"},
                      "invalid known sprite atlas item")
        key = atlas.safe_path(entry["romfs_path"]).as_posix().casefold()
        atlas.require(key not in seen, "duplicate known game atlas")
        seen.add(key)
        h = entry["original_sha256"]
        atlas.require(isinstance(h, str) and atlas.SHA.fullmatch(h) is not None,
                      "missing original graphic SHA-256")
        slots = entry["slots"]
        atlas.require(isinstance(slots, list) and 0 < len(slots) <= 512,
                      "invalid known sprite slot list")
        for sprite in slots:
            atlas.require(isinstance(sprite, dict) and set(sprite) == {"button", "rect"} and
                          sprite["button"] in atlas.ICONS and
                          isinstance(sprite["rect"], list) and
                          len(sprite["rect"]) == 4 and
                          all(type(x) is int for x in sprite["rect"]),
                          "source symbols must have known and approved buttons")
    return doc


def suggest(source_spec: Path, target_romfs: Path,
            title_id: str, update_version: str, approval: bool = False) -> dict:
    original = load_spec(source_spec)
    atlas.require(isinstance(title_id, str) and atlas.HEX16.fullmatch(title_id) is not None and
                  int(title_id, 16) != 0, "invalid target title")
    atlas.require(isinstance(update_version, str) and
                  atlas.VERSION.fullmatch(update_version) is not None,
                  "invalid target update version")
    atlas.require(target_romfs.is_dir() and not target_romfs.is_symlink(),
                  "target RomFS is invalid")

    # Include all higher-ranked image paths plus exact original paths even
    # when a huge RomFS has >200 other candidate UI graphics.
    known = {}
    for resource in atlas.discover(target_romfs, 200):
        if "original_sha256" in resource:
            known.setdefault(resource["original_sha256"].lower(), []).append(resource["romfs_path"])
    for item in original["atlases"]:
        try:
            candidate = atlas.regular(target_romfs, atlas.safe_path(item["romfs_path"]))
            if candidate.suffix.lower() in (".png", ".tga"):
                h = atlas.digest(candidate)
                known.setdefault(h.lower(), []).append(item["romfs_path"])
        except (atlas.InvalidAtlas, OSError):
            continue
    cloned = []
    for item in original["atlases"]:
        h = item["original_sha256"].lower()
        matches = sorted(set(known.get(h, [])))
        if len(matches) != 1:
            # No match or ambiguous identical atlases: fail closed instead
            # of silently choosing arbitrary UI/gameplay contexts.
            continue
        path = atlas.safe_path(matches[0])
        atlas.require(path.suffix.lower() in (".png", ".tga"),
                      "only RGBA PNG/TGA original resources may be reused")
        source_file = atlas.regular(target_romfs, path)
        atlas.require(atlas.digest(source_file).lower() == h,
                      "changed source atlas during reuse discovery")
        cloned.append({
            "romfs_path": matches[0],
            "original_sha256": h,
            "slots": [
                {"button": slot["button"] if approval else None,
                 "rect": slot["rect"][:]}
                for slot in item["slots"]
            ],
        })
    atlas.require(bool(cloned), "no unique byte-identical source game atlases found")
    return {
        "schema": 1,
        "title_id": title_id.upper(),
        "update_version": update_version,
        "variant": original["variant"],
        "atlases": cloned,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-spec", type=Path, required=True)
    p.add_argument("--target-romfs", type=Path, required=True)
    p.add_argument("--title-id", required=True)
    p.add_argument("--update-version", required=True)
    p.add_argument("--out", type=Path, required=True, help="NEW result file")
    p.add_argument("--approve-same-semantics", action="store_true",
                   help="carry over labels only after verifying SAME in-game button meanings")
    args = p.parse_args()
    try:
        atlas.require(not args.out.exists() and not args.out.is_symlink() and
                      args.out.parent.is_dir() and not args.out.parent.is_symlink(),
                      "destination already exists or parent is invalid")
        proposal = suggest(args.source_spec, args.target_romfs, args.title_id,
                           args.update_version, args.approve_same_semantics)
        args.out.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
        print(f"REUSE {args.out}: {len(proposal['atlases'])} exact atlas matches "
              f"({'approved' if args.approve_same_semantics else 'BUTTONS UNASSIGNED'})")
        return 0
    except (atlas.InvalidAtlas, OSError, ValueError) as error:
        print(f"REJECTED glyph atlas reuse: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
