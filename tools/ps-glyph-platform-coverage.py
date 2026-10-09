#!/usr/bin/env python3
"""Deterministic discovery worklist across all indexed Nintendo Switch 1 games.

Joins verified *research metadata* only. Never treats a community mod page as
proof of ROMFS compatibility or measured sprite coordinates. Outputs the
missing work for titles with and without PC/WiiU/PSP references, so the
research effort is not restricted to a hardcoded few popular games.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWITCH = ROOT / "docs/PS_GLYPH_SOURCE_INDEX.json"
OTHER = ROOT / "docs/PS_GLYPH_CROSS_PLATFORM_INDEX.json"
MAX_SIZE = 512 * 1024


def read_json(file: Path) -> dict:
    if not file.is_file() or file.is_symlink() or file.stat().st_size > MAX_SIZE:
        raise ValueError("missing, unsafe or oversized metadata")
    data = json.loads(file.read_text("utf-8"))
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("metadata schema mismatch")
    return data


def worklist(switch: dict, other: dict) -> dict:
    native = switch.get("mods")
    external = other.get("sources")
    if not isinstance(native, list) or not isinstance(external, list):
        raise ValueError("invalid metadata lists")
    switch_by_game = defaultdict(list)
    other_by_game = defaultdict(list)
    for item in native:
        if not isinstance(item, dict) or not isinstance(item.get("title"), str):
            raise ValueError("invalid Switch source")
        switch_by_game[item["title"]].append(item)
    for item in external:
        if not isinstance(item, dict) or item.get("switch_game") not in switch_by_game:
            raise ValueError("orphan cross-platform source")
        other_by_game[item["switch_game"]].append(item)
    tasks = []
    for title, records in switch_by_game.items():
        cross = other_by_game[title]
        known_switch_paths = sorted({
            lead["romfs_archive"]
            for record in records for lead in record.get("resource_leads", [])
            if isinstance(lead, dict) and isinstance(lead.get("romfs_archive"), str)
        })
        known_mod_formats = sorted({
            candidate for r in records for candidate in r.get("format_or_tool_leads", [])
            if isinstance(candidate, str)
        })
        # Purely RESEARCH priority: not quality or runtime compatibility.
        same_title = sum(x.get("relationship", "").startswith("same_title") for x in cross)
        known_named_art = sum(bool(x.get("asset_path")) for x in cross)
        priority = min(100, 12 * same_title + 8 * bool(known_switch_paths) +
                       3 * len(records) + 2 * known_named_art)
        tasks.append({
            "switch_title": title,
            "switch_mod_references": len(records),
            "additional_other_platform_references": len(cross),
            "other_platforms": sorted({x["platform"] for x in cross}),
            "known_switch_romfs_archive_hints": known_switch_paths,
            "format_and_tool_leads": known_mod_formats,
            "geometry_verified": any(x.get("rect_xywh") is not None for x in records),
            "requires_matching_game_romfs": True,
            "requires_real_mod_archive_inspection": True,
            "requires_scene_semantics_and_native_ps5_test": True,
            "priority_for_research_only": priority,
            "next_evidence": (
                "Compare same-title PC/Wii U/PSP UI mods against exact source texture"
                if same_title else
                "Find other-platform (if available) and Switch button UI asset sources"
            ),
        })
    tasks.sort(key=lambda r: (-r["priority_for_research_only"], r["switch_title"]))
    return {
        "schema": 1,
        "scope": "all games already present in Switch 1 PS glyph research index",
        "games": len(tasks),
        "games_with_other_platform_leads": sum(x["additional_other_platform_references"] > 0 for x in tasks),
        "verified_switch_atlas_rectangles": sum(x["geometry_verified"] for x in tasks),
        "worklist": tasks,
        "warning": "Priority denotes research effort only. No native Switch/PS5 compatibility follows from reference counts.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, help="NEW report only, never overwrite")
    args = p.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("unsafe output")
        result = json.dumps(worklist(read_json(SWITCH), read_json(OTHER)),
                            indent=2, ensure_ascii=False) + "\n"
        if args.out:
            args.out.write_text(result, "utf-8")
            print(f"RESEARCH WORKLIST {args.out}")
        else:
            print(result, end="")
        return 0
    except (ValueError, OSError, UnicodeError) as error:
        print(f"REJECTED cross-platform worklist: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
