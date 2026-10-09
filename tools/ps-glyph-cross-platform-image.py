#!/usr/bin/env python3
"""Propose (NEVER auto-install) PC/WiiU/PSP-to-Switch glyph pixel correspondence.

Requires user-authorized *decoded images* from:
  1. unmodified other-platform UI texture,
  2. modified other-platform UI texture,
  3. unmodified same-name Switch UI texture.

Two separate kinds of evidence are supported:
  (1) Exact decoded source/Switch original pixels: pixel candidate rectangles.
  (2) Different source/Switch original pixels but matching normalized UI
      anchor and one isolated Switch alpha sprite: layout POSITION PRIOR only.
      This is never a qualified atlas slot; a human still checks the scene
      and action before approving any game resource writes.
Fully transparent RGB padding is ignored. Even exact matches MUST have
semantic checks and verified original Switch resource/update before install.
Does not modify game files or claim engine packer compatibility.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("eden_cross_platform_diff", ROOT / "ps-glyph-mod-diff.py")
if SPEC is None or SPEC.loader is None:
    raise SystemExit("missing local ps-glyph-mod-diff.py")
diff = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diff)

SCAN_SPEC = importlib.util.spec_from_file_location("eden_cross_platform_alpha_scan",
                                                   ROOT / "ps-glyph-scan.py")
if SCAN_SPEC is None or SCAN_SPEC.loader is None:
    raise SystemExit("missing ps-glyph-scan.py")
scan = importlib.util.module_from_spec(SCAN_SPEC)
SCAN_SPEC.loader.exec_module(scan)

# Screen-space / atlas-normalized position correlation, *never a content
# identity assertion*. UI screen anchors should instead use
# ps-glyph-scene-positions.py. PNG atlas candidates stay unapproved.
MAX_ANCHOR_DISTANCE = 0.075
MIN_DIMENSION_RATIO = 0.45
MAX_DIMENSION_RATIO = 2.25


def candidate_scene_layout_positions(source_bytes: bytes, source_mod_bytes: bytes,
                                     switch_bytes: bytes) -> list[dict]:
    changes = diff.image_diff(source_bytes, source_mod_bytes)
    if changes.get("status") != "pixels_differ":
        return []
    rects = changes.get("changed_rects_xywh")
    if not isinstance(rects, list) or len(rects) > 512:
        return []
    with Image.open(io.BytesIO(source_bytes)) as source, Image.open(io.BytesIO(switch_bytes)) as nx:
        if source.format not in ("PNG", "TGA") or nx.format not in ("PNG", "TGA"):
            return []
        if source.width * source.height > diff.MAX_IMAGE_PIXELS or nx.width * nx.height > diff.MAX_IMAGE_PIXELS:
            return []
        # Only isolated original Switch sprites may become candidate
        # regions; opaque backgrounds and fonts inside complex sheets are
        # intentionally NOT guessed. Pixel/raster art may differ.
        nx_slots = scan.alpha_candidates(nx.convert("RGBA"))
        if not nx_slots:
            return []
        output, used = [], set()
        for changed in rects:
            if (not isinstance(changed, list) or len(changed) != 4 or
                any(type(n) is not int for n in changed)):
                continue
            x, y, w, h = changed
            if w <= 0 or h <= 0:
                continue
            source_center = ((x + w / 2) / source.width, (y + h / 2) / source.height)
            proposed = []
            for idx, slot in enumerate(nx_slots):
                a, b, sw, sh = slot
                center = ((a + sw / 2) / nx.width, (b + sh / 2) / nx.height)
                distance = math.hypot(center[0] - source_center[0],
                                      center[1] - source_center[1])
                expected_w, expected_h = w * nx.width / source.width, h * nx.height / source.height
                rw, rh = sw / expected_w, sh / expected_h
                if (distance <= MAX_ANCHOR_DISTANCE and
                    MIN_DIMENSION_RATIO <= rw <= MAX_DIMENSION_RATIO and
                    MIN_DIMENSION_RATIO <= rh <= MAX_DIMENSION_RATIO):
                    proposed.append((idx, slot, distance))
            # Do not select a nearby button arbitrarily if multiple
            # independent candidate sprites are plausible.
            if len(proposed) != 1 or proposed[0][0] in used:
                continue
            idx, slot, distance = proposed[0]
            used.add(idx)
            output.append({
                "source_changed_rect_xywh": changed,
                "switch_alpha_sprite_candidate_xywh": slot,
                "source_normalized_center_xy": [round(x, 8) for x in source_center],
                "switch_normalized_center_xy":
                    [round((slot[0] + slot[2] / 2) / nx.width, 8),
                     round((slot[1] + slot[3] / 2) / nx.height, 8)],
                "normalized_anchor_distance": round(distance, 8),
                "evidence": "same_game_layout_prior_only",
                "symbol_identity_verified": False,
                "verified_switch_sprite_for_installation": False,
            })
        return output



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
    # Source images often differ between platforms despite preserving
    # the same game UI positions. Reuse normalized placement separately
    # from pixel-identical candidate atlas rectangles. NOT install-ready.
    layout_candidates = candidate_scene_layout_positions(pc_data, patched_data, nx_data)
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
        "source_ui_layout_position_candidates": layout_candidates,
        "source_ui_layout_position_is_atlas_write_proof": False,
        "candidate_is_installed_or_semantically_approved": False,
        "source_container_binary_equivalence_verified": False,
        "switch_original_container_binary_verified": False,
        "switch_game_update_verified": False,
        "ps5_qualified": False,
        "warning": "Same-game UI anchors can be reused even when platform art differs; matching scene positions are layout priors only, NOT Switch texture-write coordinates. Container identity, icon semantics, version, rights and console testing remain separate.",
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
