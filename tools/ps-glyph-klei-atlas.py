#!/usr/bin/env python3
"""Read-only Klei atlas XML UV and candidate texture-space rectangle inventory.

Don't Starve Together Lua source references:
   images/ps4_controllers.xml + images/ps4_controllers.tex
   images/nx_controllers.xml  + images/nx_controllers.tex
   images/xb1_controllers.xml + images/xb1_controllers.tex

Klei atlas XML uses <Atlas><Texture filename="...tex" /> and <Elements>
<Element name="..." u1=".." u2=".." v1=".." v2=".."/>. The XML defines
*normalized UV positions*; supply genuine associated texture width/height
obtained independently. We report bottom- and top-origin pixel candidates,
not a guessed single coordinate system. We NEVER decode, copy, patch or
repack game assets, and do not interpret an element name as button semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_XML = 4 * 1024 * 1024
MAX_ELEMENTS = 8192
MAX_DIM = 16384
MAX_NAME = 256
PIXEL_EPS = 0.002


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def parse_uv(item: ET.Element, key: str) -> float:
    try:
        value = float(item.attrib[key])
    except (ValueError, KeyError) as exc:
        raise ValueError(f"missing or invalid {key} UV") from exc
    require(math.isfinite(value) and 0 <= value <= 1,
            f"{key} UV lies outside [0, 1]")
    return value


def pixel_edge(uv: float, extent: int) -> int | None:
    p = uv * extent
    rounded = round(p)
    return int(rounded) if abs(p - rounded) <= PIXEL_EPS else None


def read(filename: Path, width: int, height: int) -> dict:
    require(filename.is_file() and not filename.is_symlink(), "XML must be local regular file")
    require(type(width) is int and type(height) is int and
            0 < width <= MAX_DIM and 0 < height <= MAX_DIM,
            "texture dimensions missing/outside bounds")
    require(1 <= filename.stat().st_size <= MAX_XML, "atlas XML outside bounded size")
    raw = filename.read_bytes()
    require(len(raw) <= MAX_XML, "incomplete/oversized atlas read")
    upper = raw.upper()
    require(b"<!DOCTYPE" not in upper and b"<!ENTITY" not in upper and
            b"<?XML-STYLESHEET" not in upper,
            "external XML entities/DTD/stylesheet refused")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("invalid XML atlas") from exc
    require(root.tag == "Atlas", "unsupported Klei XML root")
    textures = root.findall("Texture")
    require(len(textures) == 1, "require exactly one atlas texture")
    texture_name = textures[0].get("filename")
    require(bool(texture_name) and len(texture_name) <= MAX_NAME and
            all(c.isprintable() for c in texture_name),
            "invalid Klei .tex reference")
    layout = root.find("Elements")
    require(layout is not None and len(layout) <= MAX_ELEMENTS,
            "missing/excessive Klei XML Elements")
    records = []
    seen = set()
    for child in layout:
        require(child.tag == "Element", "unsupported XML Elements child")
        name = child.get("name")
        require(bool(name) and len(name) <= MAX_NAME and
                all(c.isprintable() for c in name),
                "invalid atlas sprite name")
        require(name.casefold() not in seen, "duplicate case-insensitive atlas sprite")
        seen.add(name.casefold())
        u1, u2 = parse_uv(child, "u1"), parse_uv(child, "u2")
        v1, v2 = parse_uv(child, "v1"), parse_uv(child, "v2")
        require(u2 > u1 and v2 > v1, "empty or reversed UV rectangle")
        px1, px2 = pixel_edge(u1, width), pixel_edge(u2, width)
        py1, py2 = pixel_edge(v1, height), pixel_edge(v2, height)
        measured = all(edge is not None for edge in (px1, px2, py1, py2))
        rect_bottom = [px1, py1, px2 - px1, py2 - py1] if measured else None
        rect_top = [px1, height - py2, px2 - px1, py2 - py1] if measured else None
        records.append({
            "sprite_name": name,
            "normalized_uv": [u1, v1, u2, v2],
            "candidate_bottom_origin_xywh": rect_bottom,
            "candidate_top_origin_xywh": rect_top,
            "texel_grid_aligned": measured,
            "observed_sprite_button_identity": None,
            "origin_and_runtime_atlas_verified": False,
        })
    return {
        "schema": 1, "kind": "Klei_Atlas_XML_read_only",
        "xml_filename": filename.name,
        "atlas_xml_sha256": hashlib.sha256(raw).hexdigest(),
        "referenced_texture_file": texture_name,
        "externally_supplied_texture_dimensions": [width, height],
        "sprite_element_count": len(records), "elements": records,
        "game_title_update_verified": False,
        "texture_binary_sha256": None,
        "warning": "UV coordinates are from provided XML; pixel rectangles are hypothetical until .tex dimensions, UV origin, exact ROMFS version, sprite usage and on-console visuals are verified.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas-xml", type=Path, required=True)
    parser.add_argument("--texture-width", type=int, required=True)
    parser.add_argument("--texture-height", type=int, required=True)
    parser.add_argument("--out", type=Path, help="new report path (never overwrite)")
    args = parser.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("unsafe/existing output")
        report = json.dumps(read(args.atlas_xml, args.texture_width, args.texture_height),
                            indent=2, ensure_ascii=True) + "\n"
        if args.out:
            args.out.write_text(report, encoding="utf-8")
            print(f"KLEI ATLAS UV INVENTORY {args.out} (read-only)")
        else:
            print(report, end="")
        return 0
    except (OSError, ValueError) as exc:
        print(f"REJECTED Klei atlas: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
