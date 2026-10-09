#!/usr/bin/env python3
"""Reuse same-game PS/NS scene positions without confusing them with atlas pixels.

A game can retain UI anchors across PS4/PC/Wii U/Switch even when its
art atlas, texture format, sprites and file offsets differ. This tool
keeps such coordinates available as scene-level priors, not as RomFS
texture writes. It also reads existing Don't Starve Together Lua anchors.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWN = ROOT / "docs/PS_GLYPH_DST_CONTROL_UI_POSITIONS.json"
MAX_BYTES = 512 * 1024


class InvalidPosition(ValueError):
    pass


def require(condition: bool, why: str) -> None:
    if not condition:
        raise InvalidPosition(why)


def document(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size <= MAX_BYTES, "missing or unsafe scene position data")
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), "positions must be a JSON object")
    return data


def number(value: object) -> float:
    require(type(value) in (float, int) and math.isfinite(value),
            "nonfinite/non-numeric scene coordinate")
    return float(value)


def transfer(doc: dict) -> dict:
    """Project known source UI anchors into a target scene's measured bounds.

    This transforms UI geometry only. It DOES NOT infer the target game's
    texture UVs, internal sprite coordinates or its current scene.
    """
    require(doc.get("schema") == 1, "scene layout schema must be 1")
    require(isinstance(doc.get("game"), str) and 0 < len(doc["game"]) <= 160,
            "game identity required")
    require(isinstance(doc.get("scene"), str) and 0 < len(doc["scene"]) <= 100,
            "scene identity required")
    src = doc.get("source_frame")
    dst = doc.get("target_frame")
    require(isinstance(src, dict) and isinstance(dst, dict),
            "source and target scene bounds required")
    def bounds(frame: dict) -> tuple[float, float, float, float]:
        require(set(frame) == {"x", "y", "width", "height"},
                "scene frame requires x/y/width/height")
        x, y, w, h = (number(frame[k]) for k in ("x", "y", "width", "height"))
        require(0 < w <= 16384 and 0 < h <= 16384,
                "invalid viewport dimensions")
        return x, y, w, h
    ax, ay, aw, ah = bounds(src)
    bx, by, bw, bh = bounds(dst)
    anchors = doc.get("anchors")
    require(isinstance(anchors, list) and 0 < len(anchors) <= 256,
            "1-256 actual same-game scene anchors required")
    result, identifiers = [], set()
    for slot in anchors:
        require(isinstance(slot, dict) and
                set(slot) == {"id", "x", "y", "semantic", "source_proof"},
                "invalid source-scene anchor")
        label = slot["id"]
        require(isinstance(label, str) and 0 < len(label) <= 80 and
                label not in identifiers, "empty or repeated anchor id")
        identifiers.add(label)
        xx, yy = number(slot["x"]), number(slot["y"])
        require(ax <= xx <= ax + aw and ay <= yy <= ay + ah,
                "anchor not inside source scene bounds")
        require(slot["semantic"] in ("guest_action", "controller_position",
                                    "ui_label", "contextual_prompt"),
                "unrecognized scene anchor semantic")
        require(isinstance(slot["source_proof"], str) and
                8 <= len(slot["source_proof"]) <= 512 and
                slot["source_proof"].startswith("https://"),
                "traceable source anchor reference required")
        nx, ny = (xx - ax) / aw, (yy - ay) / ah
        result.append({"id": label, "semantic": slot["semantic"],
                       "source_normalized_xy": [round(nx, 8), round(ny, 8)],
                       "target_scene_xy": [round(bx + nx * bw, 4),
                                           round(by + ny * bh, 4)],
                       "source_proof": slot["source_proof"],
                       "verified_target_scene": False})
    return {"schema": 1, "game": doc["game"], "scene": doc["scene"],
            "anchors": result, "target_viewport_approved": False,
            "romfs_texture_slots": None, "active_in_emulator": False,
            "warning": ("Same-game UI placement is reusable as a scene prior. "
                        "It does not prove identical atlas coordinates, "
                        "the scene's active UI state, or installation safety.")}


def dont_starve_together() -> dict:
    """Apply documented game-source UI local transform, not screen UVs."""
    original = document(KNOWN)
    require(original.get("schema") == 1 and
            original.get("parent_controller_widget_transform", {}).get(
                "source_code_verified") is True,
            "DST source-code layout evidence missing")
    groups = original["menu_controller_help_labels"]
    parent = original["parent_controller_widget_transform"]
    shared, platform = {}, {}
    for which in ("DUALSHOCK4", "SWITCH"):
        transform = parent[which]
        position, scale = transform["position_xyz"], number(transform["scale"])
        require(0 < scale <= 5, "invalid documented widget scale")
        require(isinstance(position, list) and len(position) == 3,
                "wrong widget parent position")
        own, seen = {}, set()
        for item in groups[which]:
            key = item["string_identifier"]
            require(key not in seen and item["ui_coordinate_not_texture_pixel"] is True,
                    "ambiguous scene label")
            seen.add(key)
            x, y = number(item["label_widget_local_x"]), number(item["label_widget_local_y"])
            own[key] = [round(number(position[0]) + scale * x, 4),
                        round(number(position[1]) + scale * y, 4)]
        platform[which] = own
    for name in sorted(set(platform["SWITCH"]) & set(platform["DUALSHOCK4"])):
        a, b = platform["SWITCH"][name], platform["DUALSHOCK4"][name]
        shared[name] = {"playstation_ui_local_xy": b, "switch_ui_local_xy": a,
                        "same_position": a == b,
                        "delta_switch_to_ps4_xy": [round(b[0] - a[0], 4),
                                                   round(b[1] - a[1], 4)]}
    require(shared, "no cross-platform in-game layout positions")
    return {"schema": 1, "game": "Don't Starve Together",
            "scene": "controller_help_options",
            "source_url": original["source_url"],
            "source_layout_blob": original["source_blob_sha"],
            "platforms": ["DUALSHOCK4", "SWITCH"],
            "verified_from_source_code": True,
            "positions": shared,
            "total_common_scene_anchors": len(shared),
            "exactly_reused_positions": sum(v["same_position"] for v in shared.values()),
            "screen_pixel_positions": None,
            "romfs_atlas_rectangles": None,
            "runtime_qualified": False,
            "warning": "Game-owned Lua widget coordinates, not Switch texture sprites."}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("dst", "transfer"))
    p.add_argument("--scene", type=Path, help="cross-platform anchors for transfer")
    p.add_argument("--out", type=Path, help="write new report; no overwrites")
    args = p.parse_args()
    try:
        require(args.action != "transfer" or args.scene is not None,
                "transfer needs source/target scene evidence")
        value = dont_starve_together() if args.action == "dst" else transfer(document(args.scene))
        output = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        if args.out:
            require(args.out.parent.is_dir() and not args.out.parent.is_symlink() and
                    not args.out.exists() and not args.out.is_symlink(),
                    "output exists or unsafe")
            args.out.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        return 0
    except (InvalidPosition, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"SCENE POSITION REUSE BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
