#!/usr/bin/env python3
"""Read-only join of separate PC and Switch Unity Texture2D/Sprite inventories.

Requires JSON outputs from ps-glyph-unity-inventory.py. Exact object-name matches
are research leads; even same dimensions are NOT pixel equivalence, binding of
a runtime sprite to a texture, or an approved modification. A Sprite's Unity
serialized textureRect can expose actual engine metadata from both platforms.
No game asset decoding, extraction, alteration or copyright redistribution.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

MAX_JSON_BYTES = 6 * 1024 * 1024
MAX_REPORT = 12000


def read(file: Path) -> dict:
    if not file.is_file() or file.is_symlink() or not 1 <= file.stat().st_size <= MAX_JSON_BYTES:
        raise ValueError("invalid Unity inventory report")
    data = json.loads(file.read_text("utf-8"))
    if data.get("schema") != 1 or data.get("source") != "unity_serialized_asset_metadata" or \
            not isinstance(data.get("objects"), list) or len(data["objects"]) > MAX_REPORT:
        raise ValueError("not a bounded Unity sprite/texture inventory")
    sha = data.get("container_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or \
            any(x not in "0123456789abcdefABCDEF" for x in sha):
        raise ValueError("missing parent assets SHA-256")
    return data


def group(records: list) -> dict[tuple[str, str], list]:
    result = defaultdict(list)
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("invalid Unity object record")
        name, kind = item.get("name"), item.get("object_type")
        if not isinstance(name, str) or not name or len(name) > 256 or \
                kind not in ("Texture2D", "Sprite"):
            raise ValueError("unsafe Unity object identity")
        result[(kind, name.casefold())].append(item)
    return result


def compare(pc: dict, switch: dict) -> dict:
    if pc.get("source_platform_declared", "").lower() not in ("pc", "windows", "steam", "game pass"):
        raise ValueError("first report must explicitly declare PC source platform")
    if switch.get("source_platform_declared", "").lower() not in ("switch", "nintendo switch"):
        raise ValueError("second report must explicitly declare Switch source platform")
    pc_items, sw_items = group(pc["objects"]), group(switch["objects"])
    overlapping = []
    only_pc_playstation = []
    for key in sorted(set(pc_items) | set(sw_items)):
        pc_values, nx_values = pc_items.get(key, []), sw_items.get(key, [])
        if not pc_values or not nx_values:
            if pc_values and ("ps4" in key[1] or "ps5" in key[1] or
                              "playstation" in key[1] or "dualshock" in key[1] or
                              "dualsense" in key[1]):
                only_pc_playstation.append({"name":pc_values[0]["name"], "asset_type":key[0],
                                           "switch_counterpart_found":False})
            continue
        if len(pc_values) != 1 or len(nx_values) != 1:
            overlapping.append({"object_type":key[0], "name":pc_values[0]["name"],
                                "status":"ambiguous_duplicate_object_names",
                                "binary_verified":False})
            continue
        p, n = pc_values[0], nx_values[0]
        field = ("texture_dimensions" if key[0] == "Texture2D"
                 else "serialized_texture_rect")
        value_a, value_b = p.get(field), n.get(field)
        overlapping.append({
            "object_type":key[0], "name":p["name"],
            "status":"same_object_name_only",
            "pc_asset_path_id":p.get("path_id"), "switch_asset_path_id":n.get("path_id"),
            "pc_geometry":value_a, "switch_geometry":value_b,
            "declared_geometry_equal":bool(value_a is not None and value_a == value_b),
            "pc_sprite_rect":p.get("serialized_sprite_rect"),
            "switch_sprite_rect":n.get("serialized_sprite_rect"),
            "source_or_switch_texture_pixels_compared":False,
            "sprite_semantic_identity_confirmed":False,
        })
    return {
        "schema":1,"source":"cross_platform_Unity_serialized_metadata_join",
        "pc_container_sha256":pc["container_sha256"],
        "switch_container_sha256":switch["container_sha256"],
        "shared_object_name_count":len(overlapping),
        "shared_name_candidates":overlapping,
        "pc_only_playstation_named_assets":only_pc_playstation,
        "actual_switch_ps_texture_pixels_verified":0,
        "ps5_qualified":False,
        "warning":"Unity object and rect metadata only. Real decoded pixel identity, packing, UV origin, original game update, semantic mapping and PS5 runtime remain unverified.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pc-report", required=True, type=Path)
    p.add_argument("--switch-report", required=True, type=Path)
    p.add_argument("--out", type=Path, help="new report, never overwrite")
    args = p.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("output already exists or parent unsafe")
        result = json.dumps(compare(read(args.pc_report), read(args.switch_report)),
                            indent=2, ensure_ascii=True) + "\n"
        if args.out:
            args.out.write_text(result, encoding="utf-8")
            print(f"UNITY PLATFORM PAIR {args.out} (metadata only)")
        else:
            print(result, end="")
        return 0
    except (OSError, ValueError) as exc:
        print(f"REJECTED Unity platform pair: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
