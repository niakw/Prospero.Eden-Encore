#!/usr/bin/env python3
"""Bounded static Lua source audit for button prompt asset selection and UI labels.

No Lua execution, no binary/game extraction, no modifying game assets.
Recognises literal Asset("ATLAS"/"IMAGE", "images/...") references and
controller help LABELS rows used by some Lua-based games (e.g. Klei).
Only *textual* reference positions and local UI label coordinates are
reported; do not confuse them with texture UV/pixel rectangles or proof
that the Switch title contains those files. Heuristic branch association
is explicitly labelled, never promoted to confirmed runtime semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MAX_SOURCE = 2 * 1024 * 1024
MAX_LINES = 40000
MAX_PATHS = 8192
MAX_LABELS = 4096
ASSET = re.compile(r'\bAsset\(\s*["\'](ATLAS|IMAGE)["\']\s*,\s*["\']([^"\']{1,256})["\']\s*\)')
LABEL = re.compile(
    r'\{\s*x\s*=\s*([A-Z_]+|-?\d+)\s*,\s*y\s*=\s*(-?\d+)\s*,'
    r'\s*anchor\s*=\s*(ANCHOR_\w+)\s*,\s*text\s*='
    r'\s*STRINGS\.UI\.CONTROLSSCREEN\.(\w+)\.(\w+)')
DEVICE = re.compile(r'^\s*\[DEVICE_(DUALSHOCK4|SWITCH|VITA|XBONE)\]\s*=\s*\{')
LOCAL_CONST = re.compile(
    r'^\s*local\s+(LEFT_SIDE|RIGHT_SIDE|LEFT_SIDE_VITA|RIGHT_SIDE_VITA|LABEL_WIDTH|LABEL_HEIGHT)'
    r'\s*=\s*(-?\d+)\b')
SELECTOR = re.compile(r'(get_console_from_gamepad|F_PS4_PLAYSTATION_GLYPHS)')
BRANCH = re.compile(r'(IsPS4\(\)|IsSWITCH\(\)|IsXB1\(\)|PLATFORM_LAYOUT\s*==\s*["\'](PS4|SWITCH|XBONE)["\'])')
MAX_WIDGET_ABS = 1000000


def inspect(file: Path) -> dict:
    if (not file.is_file() or file.is_symlink() or
            not 1 <= file.stat().st_size <= MAX_SOURCE):
        raise ValueError("invalid/oversized local Lua file")
    raw = file.read_bytes()
    if len(raw) > MAX_SOURCE or b"\x00" in raw:
        raise ValueError("Lua source outside bounds or binary")
    try:
        contents = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Lua source must be UTF-8") from exc
    lines = contents.splitlines()
    if len(lines) > MAX_LINES:
        raise ValueError("too many source lines")
    constants: dict[str, int] = {}
    paths = []
    labels = []
    selector_lines = []
    current_device = None
    recent_branch = None
    recent_branch_line = -1

    for lineno, line in enumerate(lines, 1):
        cleaned = line.split("--", 1)[0]  # best-effort source scan, no Lua parser
        if not cleaned.strip():
            continue
        match = LOCAL_CONST.match(cleaned)
        if match:
            constants[match.group(1)] = int(match.group(2))
        branch = BRANCH.search(cleaned)
        if branch:
            recent_branch = branch.group(0)
            recent_branch_line = lineno
        for candidate in ASSET.finditer(cleaned):
            if len(paths) >= MAX_PATHS:
                raise ValueError("too many possible literal Lua art references")
            path = candidate.group(2)
            if any(c in path for c in "\r\n\x00") or path.startswith("/") or \
                    ".." in path.split("/") or "\\" in path:
                continue
            paths.append({
                "source_line": lineno,
                "asset_declaration_type": candidate.group(1),
                "literal_asset_path": path,
                "nearby_platform_condition_hint":
                    recent_branch if lineno - recent_branch_line <= 10 else None,
                "condition_is_static_heuristic_only": True,
            })
        if SELECTOR.search(cleaned):
            selector_lines.append({
                "source_line": lineno,
                "uses_console_selection_api": "get_console_from_gamepad" in cleaned,
                "mentions_ps4_glyph_flag": "F_PS4_PLAYSTATION_GLYPHS" in cleaned,
                "code_not_executed": True,
            })
        found_device = DEVICE.match(cleaned)
        if found_device:
            current_device = found_device.group(1)
            continue
        if current_device is not None:
            # A single block-close line, not an item record ending in "},"
            if re.fullmatch(r'\s*}\s*,?\s*', cleaned):
                current_device = None
                continue
            label = LABEL.search(cleaned)
            if label:
                if len(labels) >= MAX_LABELS:
                    raise ValueError("too many controller help labels")
                xpos = label.group(1)
                x = int(xpos) if xpos.lstrip("-").isdigit() else constants.get(xpos)
                y = int(label.group(2))
                if x is None or abs(x) > MAX_WIDGET_ABS or abs(y) > MAX_WIDGET_ABS:
                    continue
                alignment = label.group(3)
                lw = constants.get("LABEL_WIDTH")
                # Formula matches the Klei options UI code, but only applies if
                # the source really contains the label:SetPosition expression.
                confirmed_right = "v.x - LABEL_WIDTH/2 - 8" in contents
                confirmed_left = "v.x + LABEL_WIDTH/2" in contents
                widget_x = (x - lw // 2 - 8
                            if alignment == "ANCHOR_RIGHT" and lw is not None
                            and confirmed_right else
                            x + lw // 2 if alignment == "ANCHOR_LEFT"
                            and lw is not None and confirmed_left else None)
                labels.append({
                    "device": current_device,
                    "source_line": lineno,
                    "string_namespace": label.group(4),
                    "string_key": label.group(5),
                    "raw_x_expression": xpos,
                    "declared_anchor_x": x,
                    "declared_anchor_y": y,
                    "local_label_widget_x_if_formula_applies": widget_x,
                    "anchor_alignment": alignment,
                    "ui_coordinate_not_atlas_pixel": True,
                })
    return {
        "schema":1,
        "kind":"Lua_static_UI_source_inspection",
        "source_file":file.name,
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "local_constants":constants,
        "controller_asset_references":paths,
        "controller_help_label_rows":labels,
        "possible_runtime_controller_style_selectors":selector_lines,
        "original_switch_binary_verified":False,
        "atlas_sprite_uv_rectangles_verified":False,
        "runtime_PS5_verified":False,
        "warning":"Source text only, without evaluating Lua. Condition hints and UI screen layout positions cannot certify actual Switch game data or texture sprite coordinates.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lua-file", type=Path, required=True, help="local authorized Lua source text")
    p.add_argument("--out", type=Path, help="new JSON output file")
    args = p.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("output exists or parent unsafe")
        data = json.dumps(inspect(args.lua_file), indent=2, ensure_ascii=True) + "\n"
        if args.out:
            args.out.write_text(data, encoding="utf-8")
            print(f"LUA UI RESEARCH {args.out} (no code executed)")
        else:
            print(data, end="")
        return 0
    except (OSError, ValueError) as exc:
        print(f"REJECTED static Lua UI source: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
