#!/usr/bin/env python3
"""Compare game-owned PNG/TGA resources against a local Switch mod ZIP, read-only.

Report EXACT changed pixel component bounding boxes, not alleged button glyph
identities or automatically safe replacement slots. An extracted RomFS of the
matching game/update must be legitimately available locally. No asset bytes are
written, imported into Eden, or redistributed. ZIP entries are never extracted.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_000_000
MAX_IMAGE_FILES = 128
MAX_COMPONENTS = 1024
MAX_RUNS = 60000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def load_helper(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    if spec is None or spec.loader is None:
        raise ValueError(f"missing helper: {file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inventory_helper = load_helper("eden_mod_inventory", "ps-glyph-mod-inventory.py")
pack_helper = load_helper("eden_glyph_pack", "ps-glyph-pack.py")


def connected_rects(mask: Image.Image) -> tuple[list[list[int]], int]:
    """Find 8-connected EXACT pixel-change components without numpy/OpenCV.

    Coordinates are in decoded image pixels, half-open internal and XYWH
    externally. Limit run counts to prevent adversarial checkerboard inputs
    from consuming unbounded CPU/memory.
    """
    width, height = mask.size
    pixels = mask.tobytes()
    if len(pixels) != width * height:
        raise ValueError("unexpected 8-bit image mask layout")
    parent: list[int] = []
    bounds: list[list[int]] = []
    previous: list[tuple[int, int, int]] = []
    run_count = 0
    changed = 0

    def root(idx: int) -> int:
        while parent[idx] != idx:
            parent[idx] = parent[parent[idx]]
            idx = parent[idx]
        return idx

    def join(a: int, b: int) -> None:
        x, y = root(a), root(b)
        if x != y:
            parent[y] = x
            bounds[x][0] = min(bounds[x][0], bounds[y][0])
            bounds[x][1] = min(bounds[x][1], bounds[y][1])
            bounds[x][2] = max(bounds[x][2], bounds[y][2])
            bounds[x][3] = max(bounds[x][3], bounds[y][3])

    for y in range(height):
        base = y * width
        x = 0
        current: list[tuple[int, int, int]] = []
        pi = 0
        while x < width:
            while x < width and not pixels[base + x]:
                x += 1
            if x == width:
                break
            lo = x
            while x < width and pixels[base + x]:
                x += 1
            hi = x
            changed += hi - lo
            run_count += 1
            if run_count > MAX_RUNS:
                raise ValueError("too many changed-pixel runs to characterize safely")
            idx = len(parent)
            parent.append(idx)
            bounds.append([lo, y, hi, y + 1])
            while pi < len(previous) and previous[pi][1] < lo:
                pi += 1
            j = pi
            while j < len(previous) and previous[j][0] <= hi:
                before_lo, before_hi, before_idx = previous[j]
                if before_hi >= lo and before_lo <= hi:
                    join(idx, before_idx)
                j += 1
            current.append((lo, hi, idx))
        previous = current
    result = [
        [box[0], box[1], box[2] - box[0], box[3] - box[1]]
        for idx, box in enumerate(bounds) if root(idx) == idx
    ]
    if len(result) > MAX_COMPONENTS:
        raise ValueError("too many changed regions to propose glyph positions")
    result.sort(key=lambda b: (b[1], b[0], b[3], b[2]))
    return result, changed


def visible_change_mask(original: Image.Image, replacement: Image.Image) -> Image.Image:
    """Exact RGBA differences where at least one pixel has nonzero alpha.

    Avoid 8-bit premultiplication here: a one-unit RGB change at alpha=1
    can round to zero and falsely qualify a cross-platform sprite. RGB
    padding is ignored ONLY where both alpha channels are exactly zero.
    """
    if original.mode != "RGBA" or replacement.mode != "RGBA" or original.size != replacement.size:
        raise ValueError("visible difference requires same-sized RGBA images")
    old_r, old_g, old_b, old_a = original.split()
    new_r, new_g, new_b, new_a = replacement.split()
    alpha_changed = ImageChops.difference(old_a, new_a).point(
        lambda value: 255 if value else 0)
    rgb_changed = ImageChops.difference(old_r, new_r)
    for first, second in ((old_g, new_g), (old_b, new_b)):
        rgb_changed = ImageChops.lighter(rgb_changed, ImageChops.difference(first, second))
    rgb_changed = rgb_changed.point(lambda value: 255 if value else 0)
    visible = ImageChops.lighter(old_a, new_a).point(lambda value: 255 if value else 0)
    return ImageChops.lighter(alpha_changed, ImageChops.multiply(rgb_changed, visible))


def image_diff(original_bytes: bytes, replacement_bytes: bytes) -> dict:
    if (len(original_bytes) > MAX_IMAGE_BYTES or
            len(replacement_bytes) > MAX_IMAGE_BYTES):
        raise ValueError("decoded image file exceeds size bound")
    with Image.open(io.BytesIO(original_bytes)) as im_original, \
            Image.open(io.BytesIO(replacement_bytes)) as im_patch:
        if im_original.format not in ("PNG", "TGA") or im_patch.format != im_original.format:
            raise ValueError("only same-format PNG/TGA comparisons supported")
        if im_original.size != im_patch.size:
            return {"status": "dimensions_changed", "original_dimensions": list(im_original.size),
                    "replacement_dimensions": list(im_patch.size),
                    "changed_rects_xywh": None}
        width, height = im_original.size
        if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
            raise ValueError("image pixel count outside bounds")
        old, new = im_original.convert("RGBA"), im_patch.convert("RGBA")
        mask = visible_change_mask(old, new)
        rects, changed = connected_rects(mask)
        return {
            "status": "pixels_differ" if changed else "pixel_identical",
            "dimensions": [width, height],
            "changed_pixels": changed,
            "changed_rects_xywh": rects,
            "positions_meaning": "visible rendered-pixel change components (alpha-aware), not sprite slots, labels or proof of safe patch",
        }


def diff_mod(archive: Path, original_romfs: Path) -> dict:
    if not original_romfs.is_dir() or original_romfs.is_symlink():
        raise ValueError("original RomFS root missing or symlink")
    header = inventory_helper.inventory(archive)
    results = []
    attempted = 0
    with zipfile.ZipFile(archive) as z:
        for entry in header["files"]:
            relative = entry["romfs_path"]
            if not relative:
                continue
            record = {
                "archive_path": entry["archive_path"],
                "romfs_path": relative,
                "original_sha256": None, "replacement_sha256": None,
                "changed_rects_xywh": None,
            }
            if entry["extension"] not in (".png", ".tga"):
                record["status"] = "proprietary_or_other_format_unexamined"
                results.append(record)
                continue
            if attempted >= MAX_IMAGE_FILES:
                record["status"] = "candidate_scan_limit"
                results.append(record)
                continue
            attempted += 1
            try:
                relpath = pack_helper._path(relative)
                original = pack_helper._regular_file(original_romfs, relpath)
                if original.stat().st_size > MAX_IMAGE_BYTES:
                    raise ValueError("original image exceeds bound")
                with original.open("rb") as handle:
                    old = handle.read(MAX_IMAGE_BYTES + 1)
                member = z.getinfo(entry["archive_path"])
                if member.file_size > MAX_IMAGE_BYTES:
                    raise ValueError("mod image exceeds bound")
                with z.open(member, "r") as handle:
                    replacement = handle.read(MAX_IMAGE_BYTES + 1)
                if len(old) > MAX_IMAGE_BYTES or len(replacement) > MAX_IMAGE_BYTES:
                    raise ValueError("image size exceeds bound")
                record["original_sha256"] = hashlib.sha256(old).hexdigest()
                record["replacement_sha256"] = hashlib.sha256(replacement).hexdigest()
                record.update(image_diff(old, replacement))
            except (OSError, ValueError, RuntimeError, KeyError,
                    zipfile.BadZipFile, UnidentifiedImageError,
                    Image.DecompressionBombError) as error:
                record["status"] = "unverified_or_unsupported"
                record["reason"] = str(error)[:200]
            results.append(record)
    return {
        "schema": 1,
        "archive": archive.name,
        "archive_sha256": header["archive_sha256"],
        "examined_image_count": attempted,
        "resources": results,
        "semantic_button_identity": None,
        "verified_title_update": None,
        "in_game_runtime_proof": None,
        "warning": "This is an offline asset difference report, not validated PS5 glyph compatibility.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod-zip", type=Path, required=True, help="local authorized ZIP archive")
    parser.add_argument("--original-romfs", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="new JSON path only; never overwrite")
    args = parser.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("report path exists or its parent is unsafe")
        result = json.dumps(diff_mod(args.mod_zip, args.original_romfs), indent=2) + "\n"
        if args.out:
            args.out.write_text(result, encoding="utf-8")
            print(f"DIFF {args.out} (read-only original assets; no game edits)")
        else:
            print(result, end="")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"REJECTED glyph mod diff: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
