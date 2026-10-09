#!/usr/bin/env python3
"""Read-only exact ORIGINAL sprite relocation from PC/Wii U/PSP atlas to Switch.

Unlike whole-image comparison, this may find a specific source UI sprite in a
*differently arranged* Switch texture. No scaling, re-coloring, fuzzy similarity,
OCR, glyph naming or arbitrary semantic conversion is attempted.

Inputs: legally exported original source atlas, its modded variant, and
original Switch atlas in PNG/TGA. Every proposed source rectangle must contain
a visible mod change and a non-empty original sprite. The ORIGINAL source
rectangle is compared with a candidate original Switch rectangle using exact
alpha and exact RGB wherever alpha is nonzero; fully transparent RGB ignored.
Zero matches or multiple matches: FAIL CLOSED with no position proposal.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
SCRIPT = importlib.util.spec_from_file_location("eden_sprite_pixel_diff", ROOT / "ps-glyph-mod-diff.py")
if SCRIPT is None or SCRIPT.loader is None:
    raise SystemExit("missing ps-glyph-mod-diff.py")
diff = importlib.util.module_from_spec(SCRIPT)
SCRIPT.loader.exec_module(diff)

MAX_SPRITES = 64
MAX_RECT_SIDE = 1024
MAX_RECT_PIXELS = 512 * 512
MAX_ANCHOR_HITS = 100000
MAX_VERIFICATIONS = 256


def read_image(file: Path) -> tuple[Image.Image, str]:
    if (not file.is_file() or file.is_symlink() or
            not 1 <= file.stat().st_size <= diff.MAX_IMAGE_BYTES):
        raise ValueError("image missing, linked or too large")
    with file.open("rb") as stream:
        raw = stream.read(diff.MAX_IMAGE_BYTES + 1)
    if len(raw) > diff.MAX_IMAGE_BYTES:
        raise ValueError("image size exceeds bound")
    with __import__("io").BytesIO(raw) as io_stream:
        with Image.open(io_stream) as image:
            if image.format not in ("PNG", "TGA") or \
                    image.width * image.height > diff.MAX_IMAGE_PIXELS:
                raise ValueError("requires bounded exported PNG/TGA atlas")
            return image.convert("RGBA"), hashlib.sha256(raw).hexdigest()


def parse_rect(raw: str) -> list[int]:
    try:
        values = [int(part) for part in raw.split(",")]
    except ValueError as exc:
        raise ValueError("rectangle must be x,y,width,height") from exc
    if len(values) != 4 or any(value < 0 for value in values) or \
            values[2] == 0 or values[3] == 0 or \
            max(values[2:]) > MAX_RECT_SIDE or \
            values[2] * values[3] > MAX_RECT_PIXELS:
        raise ValueError("invalid or oversized source sprite rectangle")
    return values


def rect_crop(img: Image.Image, rect: list[int]) -> Image.Image:
    x, y, w, h = rect
    if x + w > img.width or y + h > img.height:
        raise ValueError("source sprite rectangle exceeds atlas dimensions")
    return img.crop((x, y, x + w, y + h))


def anchors(template: Image.Image) -> list[tuple[int, int, tuple[int,int,int,int]]]:
    """Select up to 4 diagnostic visible pixels, preferring rarer RGBA colors."""
    values = list(template.getdata())
    visible = [(index, value) for index, value in enumerate(values) if value[3] > 0]
    if not visible:
        return []
    occurrence = Counter(value for _, value in visible)
    visible.sort(key=lambda item: (occurrence[item[1]], -item[1][3], item[0]))
    selected: list[tuple[int,int,tuple[int,int,int,int]]] = []
    used_pixels = set()
    for index, pixel in visible:
        if pixel in used_pixels and len(selected) >= 2:
            continue
        selected.append((index % template.width, index // template.width, pixel))
        used_pixels.add(pixel)
        if len(selected) == 4:
            break
    return selected


def find_exact_original_sprite(source: Image.Image, switch: Image.Image) -> dict:
    if source.mode != "RGBA" or switch.mode != "RGBA":
        raise ValueError("requires RGBA texture images")
    if source.width > switch.width or source.height > switch.height:
        return {"status": "source_sprite_larger_than_switch", "switch_xywh": None}
    points = anchors(source)
    if not points:
        return {"status": "no_visible_original_sprite", "switch_xywh": None}
    sw, sh = switch.size
    tw, th = source.size
    px = switch.load()
    sx, sy, color = points[0]
    anchored = 0
    verified = 0
    matches: list[list[int]] = []
    for y in range(sh - th + 1):
        for x in range(sw - tw + 1):
            if px[x + sx, y + sy] != color:
                continue
            anchored += 1
            if anchored > MAX_ANCHOR_HITS:
                return {"status": "too_many_weak_anchors", "switch_xywh": None}
            if any(px[x + dx, y + dy] != rgba
                   for dx, dy, rgba in points[1:]):
                continue
            verified += 1
            if verified > MAX_VERIFICATIONS:
                return {"status": "too_many_candidates", "switch_xywh": None}
            candidate = switch.crop((x, y, x + tw, y + th))
            if diff.visible_change_mask(source, candidate).getbbox() is None:
                matches.append([x, y, tw, th])
                if len(matches) >= 2:
                    return {"status": "ambiguous_multiple_matches", "switch_xywh": None}
    if not matches:
        return {"status": "no_exact_original_match", "switch_xywh": None}
    return {"status": "unique_exact_original_sprite", "switch_xywh": matches[0]}


def propose(original_source: Path, modified_source: Path,
            original_switch: Path, rectangles: list[list[int]],
            game_title: str, source_platform: str, scene: str) -> dict:
    if not rectangles or len(rectangles) > MAX_SPRITES:
        raise ValueError("requires 1-64 explicit source rectangles")
    if any(not value or len(value) > 180 for value in
           (game_title, source_platform, scene)):
        raise ValueError("required title/platform/scene labels missing")
    source, source_sha = read_image(original_source)
    mod, mod_sha = read_image(modified_source)
    switch, switch_sha = read_image(original_switch)
    if source.size != mod.size:
        raise ValueError("source original and modified atlases have different sizes")
    output = []
    for rect in rectangles:
        old_crop = rect_crop(source, rect)
        changed_crop = rect_crop(mod, rect)
        changed_mask = diff.visible_change_mask(old_crop, changed_crop)
        if changed_mask.getbbox() is None:
            output.append({"source_rect_xywh": rect, "status": "no_visible_mod_change",
                           "switch_candidate_rect_xywh": None})
            continue
        located = find_exact_original_sprite(old_crop, switch)
        output.append({"source_rect_xywh": rect,
                       "status": located["status"],
                       "switch_candidate_rect_xywh": located["switch_xywh"],
                       "source_mod_changed_pixels": changed_mask.histogram()[255],
                       "source_sprite_button_label": None,
                       "semantic_mapping_verified": False,
                       "switch_original_container_verified": False})
    return {
        "schema": 1,
        "source": "cross_platform_exact_sprite_relocation",
        "game_title": game_title, "source_platform": source_platform,
        "scene": scene,
        "source_original_export_sha256": source_sha,
        "source_mod_export_sha256": mod_sha,
        "switch_original_export_sha256": switch_sha,
        "proposals": output,
        "source_and_switch_container_versions_verified": False,
        "ps5_runtime_verified": False,
        "warning": "Only original sprite image geometry matched exactly. No game-specific button semantics, container repack, original ROMFS SHA or executable PlayStation glyph pack was approved.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-original", required=True, type=Path)
    p.add_argument("--source-modified", required=True, type=Path)
    p.add_argument("--switch-original", required=True, type=Path)
    p.add_argument("--source-rect", action="append", required=True, type=parse_rect,
                   help="x,y,width,height; repeat for up to 64 source sprite slots")
    p.add_argument("--switch-game", required=True)
    p.add_argument("--source-platform", required=True)
    p.add_argument("--scene", required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("unsafe report destination")
        report = propose(args.source_original, args.source_modified,
                         args.switch_original, args.source_rect,
                         args.switch_game, args.source_platform, args.scene)
        text = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
        if args.out:
            args.out.write_text(text, encoding="utf-8")
            print(f"ORIGINAL SPRITE RELOCATION {args.out}; no game assets changed")
        else:
            print(text, end="")
        return 0
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        print(f"REJECTED exact sprite relocation: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
