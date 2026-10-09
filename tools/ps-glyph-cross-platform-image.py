#!/usr/bin/env python3
"""Propose (NEVER auto-install) PC/WiiU/PSP-to-Switch glyph pixel correspondence.

Requires user-authorized *decoded images* from:
  1. unmodified other-platform UI texture,
  2. modified other-platform UI texture,
  3. unmodified same-name Switch UI texture.

A rectangle can only be proposed for cross-platform transfer if the two
ORIGINAL textures have identical size and identical rendered RGBA pixels.
Fully transparent RGB padding is ignored, as it cannot produce a glyph.
Any different layout, scaling, compression, colors, original buttons or font
pixels refuses coordinate transfer. Even exact matches MUST have per-screen
semantic checks and original Switch resource/pack hashes before install.
Does not modify game files or claim engine packer compatibility.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("eden_cross_platform_diff", ROOT / "ps-glyph-mod-diff.py")
if SPEC is None or SPEC.loader is None:
    raise SystemExit("missing local ps-glyph-mod-diff.py")
diff = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diff)


def read(path: Path) -> tuple[bytes, str]:
    if (not path.is_file() or path.is_symlink() or
            not 1 <= path.stat().st_size <= diff.MAX_IMAGE_BYTES):
        raise ValueError("invalid or oversized decoded image")
    with path.open("rb") as source:
        data = source.read(diff.MAX_IMAGE_BYTES + 1)
    if len(data) > diff.MAX_IMAGE_BYTES:
        raise ValueError("decoded image exceeds memory guard")
    return data, hashlib.sha256(data).hexdigest()


def comparable_pixels(source_bytes: bytes, switch_bytes: bytes) -> tuple[str, bool, list[int] | None]:
    import io
    with Image.open(io.BytesIO(source_bytes)) as a, Image.open(io.BytesIO(switch_bytes)) as b:
        if a.format not in ("PNG", "TGA") or b.format not in ("PNG", "TGA"):
            raise ValueError("only independently decoded PNG/TGA texture exports")
        if a.size != b.size:
            return "dimensions_differ", False, None
        width, height = a.size
        if not (0 < width and 0 < height and width * height <= diff.MAX_IMAGE_PIXELS):
            raise ValueError("image outside pixel bound")
        old, new = a.convert("RGBA"), b.convert("RGBA")
        # Strict equivalence wherever either original has alpha > 0.
        # Rounded 8-bit premultiplication could miss low-alpha RGB changes.
        same = diff.visible_change_mask(old, new).getbbox() is None
        return ("rendered_pixels_identical" if same else "visible_pixels_differ",
                same, [width, height])


def propose(source_original: Path, source_mod: Path, switch_original: Path,
            title: str, source_platform: str, scene: str) -> dict:
    if any(not isinstance(v, str) or len(v) > 180 or not v.strip()
           for v in (title, source_platform, scene)):
        raise ValueError("nonempty game/platform/scene labels required")
    pc_data, pc_sha = read(source_original)
    patched_data, patched_sha = read(source_mod)
    nx_data, nx_sha = read(switch_original)
    original_relation, compatible, size = comparable_pixels(pc_data, nx_data)
    modified = diff.image_diff(pc_data, patched_data)
    source_rects = modified.get("changed_rects_xywh")
    proposal = (source_rects if compatible and
                modified["status"] == "pixels_differ" else None)
    return {
        "schema": 1,
        "switch_title": title,
        "source_platform": source_platform,
        "ui_scene_context": scene,
        "source_original_image_sha256": pc_sha,
        "source_mod_image_sha256": patched_sha,
        "switch_original_image_sha256": nx_sha,
        "original_texture_comparison": original_relation,
        "original_dimensions_xy": size,
        "source_mod_pixel_differences": modified,
        "switch_candidate_rects_xywh": proposal,
        "candidate_is_installed_or_semantically_approved": False,
        "source_container_binary_equivalence_verified": False,
        "switch_original_container_binary_verified": False,
        "switch_game_update_verified": False,
        "ps5_qualified": False,
        "warning": "Rendered image equivalence permits a geometry proposal ONLY. Container offset, texture identity, semantic button map, update compatibility, rights and console rendering require separate evidence.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-original", type=Path, required=True)
    parser.add_argument("--source-modified", type=Path, required=True)
    parser.add_argument("--switch-original", type=Path, required=True)
    parser.add_argument("--switch-game", required=True)
    parser.add_argument("--source-platform", required=True)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--out", type=Path, help="new JSON report file only")
    a = parser.parse_args()
    try:
        if a.out and (a.out.exists() or a.out.is_symlink() or
                      not a.out.parent.is_dir() or a.out.parent.is_symlink()):
            raise ValueError("unsafe existing report path")
        result = json.dumps(propose(a.source_original, a.source_modified,
                                    a.switch_original, a.switch_game,
                                    a.source_platform, a.scene), indent=2) + "\n"
        if a.out:
            a.out.write_text(result, "utf-8")
            print(f"CROSS PLATFORM GLYPH PROPOSAL {a.out} (no game resources modified)")
        else:
            print(result, end="")
        return 0
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        print(f"REJECTED cross-platform glyph comparison: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
