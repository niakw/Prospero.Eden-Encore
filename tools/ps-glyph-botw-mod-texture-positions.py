#!/usr/bin/env python3
"""Recover Switch glyph sprite candidates directly from existing UI-mod BNTX textures.

Read an authorized original BOTW Switch Yaz0/SARC UI archive and matching
modded counterpart, decode changed ASTC textures and compare their *rendered*
pixels. Public PS4/Wii U scene positions can help match actions, but the
original Switch atlas gives the final exact XYWH. No copied third-party mod
textures are output, and no Nintendo gameplay controls are guessed.

Matching a changed glyph region to one isolated original alpha sprite is
evidence for a POSITION, not proof that the glyph corresponds to action A.
An explicit per-scene guest-action/controller-position review is still needed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
MAX_CHANGED_TEXTURES = 64
MAX_PROPOSED_SLOTS = 512
MAX_COMPONENTS = 1024


def module(name: str, path: str):
    sp = importlib.util.spec_from_file_location(name, HERE / path)
    if sp is None or sp.loader is None:
        raise ValueError("missing source analysis tool " + path)
    res = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(res)
    return res


archive = module("eden_real_mod_archive", "ps-glyph-botw-archive-diff.py")
astc = module("eden_real_mod_astc", "ps-glyph-bntx-astc.py")
diff = module("eden_real_mod_pixel_diff", "ps-glyph-mod-diff.py")
scan = module("eden_real_mod_alpha_sprites", "ps-glyph-scan.py")


def contained(outer: list[int], inner: list[int]) -> bool:
    x, y, w, h = outer
    a, b, c, d = inner
    return x <= a and y <= b and a + c <= x + w and b + d <= y + h


def evidence(original_path: Path, mod_path: Path,
             scene: str, astcenc: str = "astcenc") -> dict:
    raw_old, _, _ = archive.load_archive(original_path)
    raw_new, _, _ = archive.load_archive(mod_path)
    return evidence_bytes(raw_old, raw_new, scene, astcenc)


def evidence_bytes(raw_old: bytes, raw_new: bytes, scene: str,
                   astcenc: str = "astcenc") -> dict:
    """Diff original and modded SARC/Yaz0 bytes directly, without extraction.

    Used to inspect original RomFS plus ZIP-contained Switch mods. It returns
    only hashes, sprite coordinates and semantic unknowns, never game bytes.
    """
    if scene not in ("menu", "gameplay", "hud", "tutorial", "controller_diagram",
                     "world_interaction", "pause", "special_action"):
        raise ValueError("unknown scene context")
    if (not isinstance(raw_old, bytes) or not isinstance(raw_new, bytes) or
        len(raw_old) > archive.botw.MAX_INPUT or len(raw_new) > archive.botw.MAX_INPUT):
        raise ValueError("original/mod UI source exceeds bounded archive budget")
    original = archive.botw.decode(raw_old) if raw_old.startswith(b"Yaz0") else raw_old
    patched = archive.botw.decode(raw_new) if raw_new.startswith(b"Yaz0") else raw_new
    source_meta = archive.botw.sarc.inventory_bytes(original)
    mod_meta = archive.botw.sarc.inventory_bytes(patched)
    original_members = {x["name"].casefold(): x for x in source_meta["members"] if x["name"]}
    mod_members = {x["name"].casefold(): x for x in mod_meta["members"] if x["name"]}
    if len(original_members) != len([x for x in source_meta["members"] if x["name"]]) or (
        len(mod_members) != len([x for x in mod_meta["members"] if x["name"]])
    ):
        raise ValueError("duplicate SARC member casefold name")
    candidates, unresolved = [], []
    for key in sorted(set(original_members) & set(mod_members)):
        src_member, mod_member = original_members[key], mod_members[key]
        name = src_member["name"]
        if not name.lower().endswith(".bntx"):
            continue
        src_bytes = archive.member_data(original, src_member)
        mod_bytes = archive.member_data(patched, mod_member)
        if src_bytes == mod_bytes:
            continue
        if len(candidates) + len(unresolved) >= MAX_CHANGED_TEXTURES:
            unresolved.append({"member": name, "reason": "resource_scan_budget"})
            break
        try:
            src_info = astc.tile.inspect.inspect(src_bytes)
            mod_info = astc.tile.inspect.inspect(mod_bytes)
            src_names = {x["name"].casefold(): x["name"] for x in src_info["textures"]}
            mod_names = {x["name"].casefold(): x["name"] for x in mod_info["textures"]}
            if len(src_names) != src_info["texture_count"] or (
                len(mod_names) != mod_info["texture_count"]
            ):
                raise ValueError("duplicate BNTX texture names")
        except (astc.tile.inspect.InvalidBntx, ValueError) as exc:
            unresolved.append({"member": name, "reason": "invalid_bntx",
                               "detail": str(exc)[:120]})
            continue
        for texture_key in sorted(set(src_names) & set(mod_names)):
            src_name = src_names[texture_key]
            target_name = mod_names[texture_key]
            try:
                source_desc = astc.inspect_astc(src_bytes, src_name)
                mod_desc = astc.inspect_astc(mod_bytes, target_name)
                for field in ("width", "height", "format_code",
                              "block_width", "block_height"):
                    if source_desc[field] != mod_desc[field]:
                        raise ValueError("texture dimensions/ASTC block format changed")
                old_blocks = astc.get_blocks(src_bytes, source_desc)
                new_blocks = astc.get_blocks(mod_bytes, mod_desc)
                if old_blocks == new_blocks:
                    continue
                original_pixels = astc.decoded_image(src_bytes, src_name, astcenc)
                mod_pixels = astc.decoded_image(mod_bytes, target_name, astcenc)
                rgba_diff = diff.visible_change_mask(original_pixels, mod_pixels)
                components, changed_count = diff.connected_rects(rgba_diff)
                if len(components) > MAX_COMPONENTS:
                    raise ValueError("too many modded UI difference components")
                # Use ACTUAL original Switch alpha regions to infer complete
                # sprite rectangles around the diff; do not use console-wide
                # widget coordinates as BNTX internal byte/pixel offsets.
                sprites = scan.alpha_candidates(original_pixels)
                matched: dict[tuple[int, int, int, int], int] = {}
                leftovers = []
                for rect in components:
                    possible = [tuple(sprite) for sprite in sprites
                                if contained(sprite, rect)]
                    if len(possible) == 1:
                        matched[possible[0]] = matched.get(possible[0], 0) + 1
                    else:
                        leftovers.append(rect)
                valid_slots = [{
                    "rect_xywh": list(rect), "kind": None,
                    "guest_button": None, "controller_face": None,
                    "mod_changed_components_inside": parts,
                    "action_semantics_reviewed": False
                } for rect, parts in sorted(matched.items())]
                candidates.append({
                    "member": name, "texture": src_name, "scene": scene,
                    "original_bntx_sha256": hashlib.sha256(src_bytes).hexdigest(),
                    "mod_bntx_sha256": hashlib.sha256(mod_bytes).hexdigest(),
                    "source_original_archive_sha256": hashlib.sha256(raw_old).hexdigest(),
                    "mod_archive_sha256": hashlib.sha256(raw_new).hexdigest(),
                    "original_width": source_desc["width"],
                    "original_height": source_desc["height"],
                    "astc_format": source_desc["format_code"],
                    "changed_rendered_pixels": changed_count,
                    "changed_components_xywh": components,
                    "detected_original_switch_slots": valid_slots,
                    "unmatched_changed_components_xywh": leftovers,
                    "replacement_graphics_from_mod_copied": False,
                    "ready_to_install": False,
                })
                if len(candidates) >= MAX_CHANGED_TEXTURES:
                    break
            except (ValueError, astc.UnsafeAstc, astc.tile.InvalidTexture,
                    astc.tile.inspect.InvalidBntx, OSError) as exc:
                unresolved.append({"member": name, "texture": src_name,
                                   "reason": "unsupported_or_unmatched_astc_texture",
                                   "detail": str(exc)[:140]})
        if len(candidates) >= MAX_CHANGED_TEXTURES:
            break
    return {
        "schema": 1,
        "original_archive_sha256": hashlib.sha256(raw_old).hexdigest(),
        "modified_archive_sha256": hashlib.sha256(raw_new).hexdigest(),
        "scene": scene,
        "changed_texture_count": len(candidates),
        "textures": candidates,
        "unresolved": unresolved,
        "ui_sprite_position_proposals": sum(len(x["detected_original_switch_slots"])
                                            for x in candidates),
        "usable_for_patch_without_semantic_review": False,
        "warning": ("Exact changed atlas pixel locations are recovered directly "
                    "from real Switch mod/original ASTC artwork. Slot actions, "
                    "original game/update identity, legal artwork source and "
                    "hardware UI appearance require separate verification."),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--modded", type=Path, required=True)
    p.add_argument("--scene", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--astcenc", default="astcenc")
    args = p.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink() or not args.out.parent.is_dir() or (
            args.out.parent.is_symlink()
        ):
            raise ValueError("output must be new with ordinary parent")
        result = evidence(args.original, args.modded, args.scene, args.astcenc)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print("DIRECT MOD SWITCH ASTC POSITIONS",
              result["ui_sprite_position_proposals"], "candidates across",
              result["changed_texture_count"], "changed textures; labels unreviewed")
        return 0
    except (OSError, ValueError, archive.UnsafeArchive,
            archive.botw.InvalidYaz0, archive.botw.sarc.InvalidSarc) as exc:
        print("REJECTED MOD POSITIONS", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
