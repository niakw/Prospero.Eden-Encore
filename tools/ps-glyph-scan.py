#!/usr/bin/env python3
"""Find plausible isolated glyph rectangles in locally extracted RGBA atlases.

This is a *read-only*, offline proposal stage for Eden Encore PlayStation glyphs.
It never identifies a Nintendo button, never assigns a PlayStation symbol, and
never edits a game texture. A human/validated per-title mapping is required
before tools/ps-glyph-atlas.py may render a safe mod.

Algorithm: project nontransparent alpha pixels into horizontal/vertical bands,
then split those bands on fully transparent rows/columns. Compare XY and YX
orders, keeping candidate rectangles with a transparent safety border.
Works for many sprite sheets with whitespace separation, not opaque/compressed
BNTX/BFRES or glyphs baked into 3D meshes and font texture pages.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("eden_ps_glyph_atlas", ROOT / "tools/ps-glyph-atlas.py")
if SPEC is None or SPEC.loader is None:
    raise SystemExit("Cannot locate ps-glyph-atlas.py")
atlas = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(atlas)
BNTX_SPEC = importlib.util.spec_from_file_location(
    "eden_ps_glyph_bntx", ROOT / "tools/ps-glyph-bntx-inspect.py")
if BNTX_SPEC is None or BNTX_SPEC.loader is None:
    raise SystemExit("Cannot locate ps-glyph-bntx-inspect.py")
bntx = importlib.util.module_from_spec(BNTX_SPEC)
BNTX_SPEC.loader.exec_module(bntx)

MAX_SCANNED_FILES = 64
MAX_BNTX_CONTAINERS = 32
MAX_SCAN_PIXELS = 4_000_000
MAX_RECTS = 512
ALPHA_THRESHOLD = 16
MIN_SIDE = 10
MAX_SIDE = 512
PADDING = 2


def spans(projection: list[int] | tuple[int, ...]) -> list[tuple[int, int]]:
    """Contiguous nonzero spans, expressed as half-open [lo,hi) indices."""
    found = []
    start = None
    for index, on in enumerate([*projection, 0]):
        if on and start is None:
            start = index
        elif not on and start is not None:
            found.append((start, index))
            start = None
    return found


def split_alpha(mask: Image.Image, row_first: bool) -> list[tuple[int, int, int, int]]:
    """Split alpha runs in two orthogonal passes (candidate pixels only)."""
    px, py = mask.getprojection()
    rectangles = []
    if row_first:
        for y0, y1 in spans(py):
            strip = mask.crop((0, y0, mask.width, y1))
            columns, _ = strip.getprojection()
            for x0, x1 in spans(columns):
                rectangles.append((x0, y0, x1, y1))
    else:
        for x0, x1 in spans(px):
            strip = mask.crop((x0, 0, x1, mask.height))
            _, rows = strip.getprojection()
            for y0, y1 in spans(rows):
                rectangles.append((x0, y0, x1, y1))
    return rectangles


def alpha_candidates(image: Image.Image) -> list[list[int]]:
    """Geometry only; returned regions must NOT be auto-labeled as buttons."""
    if image.mode != "RGBA" or image.width * image.height > MAX_SCAN_PIXELS:
        return []
    alpha = image.getchannel("A")
    # C-backed image threshold/projections, no Python per-pixel flood fill.
    mask = alpha.point(lambda value: 255 if value > ALPHA_THRESHOLD else 0)
    box = mask.getbbox()
    if box is None or box == (0, 0, image.width, image.height):
        return []
    options = []
    for row_first in (True, False):
        proposed = []
        for x0, y0, x1, y1 in split_alpha(mask, row_first):
            width = x1 - x0
            height = y1 - y0
            if not (MIN_SIDE <= width <= MAX_SIDE and
                    MIN_SIDE <= height <= MAX_SIDE):
                continue
            # Require a fully transparent 2-pixel perimeter around an
            # isolated island. Never clear overlapping UI artwork.
            if (x0 < PADDING or y0 < PADDING or
                    x1 + PADDING > image.width or
                    y1 + PADDING > image.height):
                continue
            rect = [x0 - PADDING, y0 - PADDING,
                    width + 2 * PADDING, height + 2 * PADDING]
            proposed.append(rect)
        # Candidate sheets should have independent, nonoverlapping regions.
        unique = []
        for rect in sorted(proposed):
            if not any(atlas.overlaps(tuple(rect), tuple(prev)) for prev in unique):
                unique.append(rect)
        if len(unique) <= MAX_RECTS:
            options.append(unique)
    # Return the richer geometry split, never a guessed symbol identity.
    return max(options, key=len, default=[])


def scan(root: Path, limit: int = MAX_SCANNED_FILES) -> dict:
    atlas.require(1 <= limit <= MAX_SCANNED_FILES, "scan limit must be 1-64")
    source_items = atlas.discover(root, limit=200)
    results = []
    inspected = 0
    for source in source_items:
        if inspected >= limit:
            break
        if source.get("mode") != "RGBA" or "original_sha256" not in source:
            continue
        relative = atlas.safe_path(source["romfs_path"])
        file = atlas.regular(root, relative)
        inspected += 1
        try:
            with Image.open(file) as img:
                if img.width * img.height > MAX_SCAN_PIXELS:
                    continue
                glyphs = alpha_candidates(img)
        except (OSError, ValueError, Image.DecompressionBombError,
                UnidentifiedImageError):
            continue
        if not glyphs:
            continue
        results.append({
            "romfs_path": relative.as_posix(),
            "original_sha256": source["original_sha256"],
            "dimensions": source["dimensions"],
            "candidate_count": len(glyphs),
            # The render spec requires a non-null 'button'. These are
            # UNRESOLVED until validated against real in-game prompts.
            "slots": [{"button": None, "rect": rect} for rect in glyphs],
            "status": "geometry_only_requires_button_identification",
        })
    # BNTX is the dominant compressed/tiling container in many titles.
    # Inspect a bounded number of file headers and internal BRTI records.
    # NO graphics decoding, atlas extraction or mutation occurs here.
    bntx_reports = []
    for source in source_items:
        if len(bntx_reports) >= MAX_BNTX_CONTAINERS:
            break
        if not source["romfs_path"].lower().endswith(".bntx"):
            continue
        relative = atlas.safe_path(source["romfs_path"])
        file = atlas.regular(root, relative)
        try:
            metadata = bntx.inspect(file)
            selected = [t for t in metadata["textures"] if t["candidate_name"]]
            bntx_reports.append({
                "romfs_path": relative.as_posix(),
                "texture_count": metadata["texture_count"],
                "candidate_texture_count": len(selected),
                "textures": selected[:32],
                "state": "requires_BNTX_deswizzle_and_format_aware_repacker",
            })
        except (bntx.InvalidBntx, OSError, ValueError):
            bntx_reports.append({
                "romfs_path": relative.as_posix(),
                "state": "unrecognized_or_incompatible_BNTX_header",
            })
    return {
        "schema": 1,
        "source_type": "read_only_rgba_and_BNTX_texture_proposals",
        "total_discovered": len(source_items),
        "files_inspected": inspected,
        "candidate_atlases": results,
        "bntx_containers": bntx_reports,
        "safety": "NO ART MODIFIED; no Nintendo->PlayStation mapping inferred",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-romfs", type=Path, required=True)
    p.add_argument("--out", type=Path, help="new JSON report; stdout if omitted")
    p.add_argument("--limit", type=int, default=MAX_SCANNED_FILES,
                   help="maximum RGBA source images inspected (1-64)")
    args = p.parse_args()
    try:
        report = scan(args.original_romfs, args.limit)
        result = json.dumps(report, indent=2) + "\n"
        if args.out:
            atlas.require(not args.out.exists() and not args.out.is_symlink() and
                          args.out.parent.is_dir() and not args.out.parent.is_symlink(),
                          "output already exists or output parent invalid")
            args.out.write_text(result, encoding="utf-8")
            print(f"CANDIDATES {args.out}: {len(report['candidate_atlases'])} RGBA atlas sheets, "
                  f"{len(report['bntx_containers'])} BNTX inventories (ALL UNVERIFIED)")
        else:
            print(result, end="")
        return 0
    except (atlas.InvalidAtlas, OSError, ValueError) as e:
        print(f"REJECTED glyph scan: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
