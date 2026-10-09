#!/usr/bin/env python3
"""Compare the named UI slots of two read-only Klei atlas XML reports.

The input must be JSON output from ps-glyph-klei-atlas.py, one from
PlayStation and one from Nintendo Switch. A shared XML Element name shows
a candidate logical sprite identity and reveals its two sets of atlas
UV/rect coordinates. It NEVER proves the art pixels, mapping/semantics or
that another-platform .tex can replace a Switch game file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_REPORT_BYTES = 6 * 1024 * 1024
MAX_ELEMENTS = 8192


def report(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or \
            not 1 <= path.stat().st_size <= MAX_REPORT_BYTES:
        raise ValueError("report missing, symlink or oversized")
    data = json.loads(path.read_text("utf-8"))
    if not isinstance(data, dict) or data.get("schema") != 1 or \
            data.get("kind") != "Klei_Atlas_XML_read_only" or \
            not isinstance(data.get("elements"), list) or \
            len(data["elements"]) > MAX_ELEMENTS:
        raise ValueError("not a valid Klei atlas report")
    digest = data.get("atlas_xml_sha256")
    if not isinstance(digest, str) or not re.fullmatch("[0-9a-fA-F]{64}", digest):
        raise ValueError("missing source atlas XML digest")
    return data


def names(data: dict) -> dict[str, dict]:
    result = {}
    for item in data["elements"]:
        if not isinstance(item, dict):
            raise ValueError("invalid element record")
        name = item.get("sprite_name")
        if not isinstance(name, str) or not 1 <= len(name) <= 256:
            raise ValueError("invalid sprite name")
        key = name.casefold()
        if key in result:
            raise ValueError("duplicate/case-colliding sprite name")
        result[key] = item
    return result


def compare(playstation: dict, switch: dict) -> dict:
    ps, nx = names(playstation), names(switch)
    matches = []
    for name in sorted(set(ps) & set(nx)):
        left, right = ps[name], nx[name]
        matches.append({
            "shared_sprite_name":left["sprite_name"],
            "ps_normalized_uv":left.get("normalized_uv"),
            "switch_normalized_uv":right.get("normalized_uv"),
            "ps_candidate_top_origin_xywh":left.get("candidate_top_origin_xywh"),
            "switch_candidate_top_origin_xywh":right.get("candidate_top_origin_xywh"),
            "ps_candidate_bottom_origin_xywh":left.get("candidate_bottom_origin_xywh"),
            "switch_candidate_bottom_origin_xywh":right.get("candidate_bottom_origin_xywh"),
            "same_normalized_uv":left.get("normalized_uv") == right.get("normalized_uv"),
            "same_reported_texture_dimensions":
                playstation.get("externally_supplied_texture_dimensions") ==
                switch.get("externally_supplied_texture_dimensions"),
            "glyph_identity_and_console_proof":False,
        })
    return {
        "schema":1,
        "kind":"Klei_cross_platform_UI_atlas_name_join",
        "ps_atlas_xml_sha256":playstation["atlas_xml_sha256"],
        "switch_atlas_xml_sha256":switch["atlas_xml_sha256"],
        "shared_sprite_names":len(matches),
        "only_in_ps_name_count":len(ps.keys()-nx.keys()),
        "only_in_switch_name_count":len(nx.keys()-ps.keys()),
        "shared":matches,
        "confirmed_switch_game_binary_sha256":None,
        "activated_glyph_overrides":0,
        "warning":"The XML sprite names/UVs were compared without verifying .tex pixels, alpha, art semantics, coordinate orientation, Switch game update or PS5 runtime.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ps-report", type=Path, required=True)
    parser.add_argument("--switch-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="NEW report path only")
    args = parser.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("output exists or parent is unsafe")
        rendered = json.dumps(compare(report(args.ps_report), report(args.switch_report)),
                              indent=2, ensure_ascii=True) + "\n"
        if args.out:
            args.out.write_text(rendered, encoding="utf-8")
            print(f"KLEI CROSS ATLAS {args.out} (read-only)")
        else:
            print(rendered, end="")
        return 0
    except (OSError, ValueError) as exc:
        print(f"REJECTED Klei platform atlas pairing: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
