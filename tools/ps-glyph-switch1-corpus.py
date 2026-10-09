#!/usr/bin/env python3
"""Merge broad Switch 1 TitleDB regional metadata into bounded discovery catalog.

All regions are metadata-only. Do not download NSP/XCI, DLC or ROMFS.
A title ID is a discovery identifier, not a per-version compatibility proof.
Uses the conservative Switch-1 base application resolver already in Eden.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("eden_switch_title_meta",
                                               HERE / "ps-glyph-switch1-titledb.py")
if spec is None or spec.loader is None:
    raise SystemExit("missing title DB resolver")
titledb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(titledb)
MAX_REGION_FILES = 24
MAX_GAME_ROWS = 250000

def merge(regions: list[Path], known: list[str] | None = None) -> dict:
    if not 1 <= len(regions) <= MAX_REGION_FILES:
        raise ValueError("need 1-24 regional title databases")
    known = known or []
    aliases = {titledb.clean_name(x) for x in known if titledb.clean_name(x)}
    names: dict[str, set[str]] = {}
    sources = []
    for region in regions:
        records, digest = titledb.read_json(region, titledb.MAX_DB_BYTES)
        count = 0
        for _, tid, displayed in titledb.entries(records):
            names.setdefault(tid, set()).add(displayed)
            count += 1
            if len(names) > MAX_GAME_ROWS:
                raise ValueError("Switch 1 catalog too large")
        sources.append({"filename": region.name, "sha256": digest, "region_rows": count})
    if not names:
        raise ValueError("no Switch-1 base games in supplied TitleDB")
    items = []
    for tid, alternatives in names.items():
        labels = sorted(alternatives, key=lambda x: (len(x), x.casefold()))
        exact_match = next((x for x in labels if titledb.clean_name(x) in aliases), None)
        # A titleID may have multiple regional titles (not separate games).
        name = exact_match or labels[0]
        items.append({"title_id": tid, "title": name, "aliases": labels[:12],
                      "previously_researched_title": bool(exact_match),
                      "game_update_verified": False, "glyph_pack_validated": False})
    items.sort(key=lambda x: (not x["previously_researched_title"],
                              x["title"].casefold(), x["title_id"]))
    return {"schema": 1, "scope": "switch1_metadata_all_supplied_regions",
            "game_count": len(items), "source_regions": sources,
            "games": items, "glyph_compatible_games": 0,
            "warning": "TitleDB name/ID metadata is not a ROMFS, scene or glyph compatibility test."}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--regions", nargs="+", required=True, type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink() or not args.out.parent.is_dir():
            raise ValueError("output must be new")
        old = json.loads((HERE.parent / "docs/PS_GLYPH_SOURCE_INDEX.json").read_text())
        seeds = json.loads((HERE.parent / "docs/PS_GLYPH_SWITCH1_GAME_SEEDS.json").read_text())
        research = [x["title"] for x in old["mods"]] + [
            x["switch_game"] for x in seeds["games"]]
        catalog = merge(args.regions, research)
        args.out.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))+"\n")
        print("SWITCH 1 METADATA:", catalog["game_count"], "base games across",
              len(catalog["source_regions"]), "regional files; zero glyph activations")
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print("INVALID SWITCH1 CATALOG:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
