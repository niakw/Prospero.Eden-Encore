#!/usr/bin/env python3
"""Index Switch 1 software from public regional metadata, never Switch 2-only.

Only base application IDs with the Switch 1 platform prefix 0100 are
eligible. Native Nintendo Switch 2-only games use 0400 and are excluded;
a Switch 1 release remains in scope even if it also has a Switch 2 Edition.
A Title ID is NOT necessarily one commercially distinct, fully released
game (region variants, demos, early listings and delisted titles exist).
No NSP/XCI, DLC, game mods or ROMFS are downloaded.
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
            "platform_filter": "Switch 1 base applications (0100), not Switch 2-only (0400)",
            "includes_switch1_games_also_on_switch2": True,
            "includes_switch2_exclusive_games": False,
            "count_unit": "regional_deduplicated_base_title_ids_not_individual_games",
            "game_count": len(items), "source_regions": sources,
            "games": items, "glyph_compatible_games": 0,
            "warning": ("TitleDB 0100 records are candidate Switch1 title IDs, not a "
                        "verified count of distinct released commercial games. "
                        "Other platforms, DLC, game-update and Switch2-only 0400 "
                        "IDs must never enter native Switch 1 glyph matching.")}

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
        print("SWITCH 1 METADATA:", catalog["game_count"],
              "candidate Switch1 base TITLE IDs (not official unique games) across",
              len(catalog["source_regions"]),
              "regions; 0400 Switch2-only excluded; zero glyph activations")
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print("INVALID SWITCH1 CATALOG:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
