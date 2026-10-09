#!/usr/bin/env python3
"""Find same-game, BUILT-IN PlayStation/Nintendo/Xbox asset name families in RomFS.

Works from a legitimately obtained, locally extracted Switch ROMFS. Many
multiplatform games embed multiple platform glyph sets even when the Switch UI
does not expose an option. This scans NAMES ONLY and never concludes that an
asset is loaded or that a source texture can be replaced.
No extraction, network request, game modification or binary decoding.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

MAX_ENTRIES = 100000
MAX_GROUPS = 512
MAX_PATH = 512
PLATFORMS = {
    "playstation": {"playstation", "dualshock", "dualsense", "ps4", "ps5", "ds4", "ds5"},
    "nintendo": {"nintendo", "switch", "joycon", "nx", "procontroller"},
    "xbox": {"xbox", "xinput", "xbone", "xone", "x360", "seriesx"},
}
ART_TERMS = {"button", "buttons", "btn", "btns", "key", "keys", "prompt", "prompts",
             "glyph", "glyphs", "controller", "controllers", "pad", "gamepad",
             "input", "icon", "icons", "control", "controls", "dpad", "hud"}
ALL_PLATFORM_TOKENS = set().union(*PLATFORMS.values())


def tokens(name: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", name.casefold()) if part]


def classify(relative: str) -> tuple[str | None, str | None]:
    p = Path(relative)
    stem_tokens = tokens(p.stem)
    # Restrict classification to exact tokens, not substrings like 'ps' in
    # 'oops', and require a controller/icon context in basename/parent.
    all_tokens = tokens(relative)
    categories = {kind for kind, lexicon in PLATFORMS.items()
                  if any(tok in lexicon for tok in all_tokens)}
    if len(categories) != 1 or not any(tok in ART_TERMS for tok in all_tokens):
        return None, None
    category = next(iter(categories))
    # Group variants sharing the same relative context, extension and
    # descriptive non-platform tokens; distinguish actual page/source folders.
    reduced = [token for token in all_tokens if token not in ALL_PLATFORM_TOKENS]
    # At least a distinctive controller/icon term must remain after stripping.
    if not any(token in ART_TERMS for token in reduced):
        return None, None
    suffix = p.suffix.lower()
    key = "/".join(reduced) + "|" + suffix
    return category, key


def discover(root: Path) -> dict:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("ROMFS root missing or symlink")
    found: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    inspected = 0
    for folder, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames.sort()
        parent = Path(folder)
        for dirname in dirnames:
            if (parent / dirname).is_symlink():
                raise ValueError("symlink directory in RomFS")
        for filename in filenames:
            file = parent / filename
            inspected += 1
            if inspected > MAX_ENTRIES:
                raise ValueError("ROMFS file inventory count exceeded")
            if file.is_symlink() or not file.is_file():
                raise ValueError("nonregular or linked game asset")
            rel = file.relative_to(root).as_posix()
            if len(rel) > MAX_PATH:
                continue
            category, key = classify(rel)
            if key:
                found[key][category].append(rel)
    groups = []
    for key in sorted(found):
        family = found[key]
        if len(family) < 2:
            continue
        groups.append({
            "normalized_name_family": key,
            "platform_asset_name_candidates": {name: sorted(files)
                                               for name, files in sorted(family.items())},
            "asset_bytes_compared": False,
            "icon_semantics_known": False,
        })
        if len(groups) >= MAX_GROUPS:
            break
    return {
        "schema": 1,
        "source": "local_switch_romfs_filename_scan",
        "inspected_files": inspected,
        "multiplatform_name_families": groups,
        "verified_same_texture_geometry": 0,
        "warning": "Filename pairs alone do NOT establish that the files are glyph sprites, are used by the game, or share atlas geometry.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--romfs", type=Path, required=True)
    p.add_argument("--out", type=Path, help="NEW JSON report file")
    args = p.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("invalid existing report path")
        report = json.dumps(discover(args.romfs), ensure_ascii=False, indent=2) + "\n"
        if args.out:
            args.out.write_text(report, "utf-8")
            print(f"BUILTIN PROMPT SOURCES {args.out} (read-only)")
        else:
            print(report, end="")
        return 0
    except (ValueError, OSError) as exc:
        print(f"REJECTED builtin prompt discovery: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
