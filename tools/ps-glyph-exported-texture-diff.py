#!/usr/bin/env python3
"""Diff externally decoded texture PNG/TGA pairs from proprietary game assets.

For example: export 'controller_btns_outlined' Texture2D from original and
patched Unity Data/resources.assets using AssetStudioMod/UABEA. The same
workflow can inspect independently decoded BNTX, BFRES, SARC-contained or
Unity sprites; it never touches the game containers or injects any assets.

Output contains actual visible changed-pixel XYWH rectangles but NOT proven
Nintendo->PlayStation semantic button names nor safe LayeredFS slots.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("eden_ps_glyph_mod_diff", BASE / "ps-glyph-mod-diff.py")
if spec is None or spec.loader is None:
    raise SystemExit("missing ps-glyph-mod-diff.py")
diff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diff)


def read(file: Path) -> tuple[bytes, str]:
    if not file.is_file() or file.is_symlink() or file.stat().st_size > diff.MAX_IMAGE_BYTES:
        raise ValueError(f"invalid/oversized texture image: {file}")
    with file.open("rb") as source:
        data = source.read(diff.MAX_IMAGE_BYTES + 1)
    if len(data) > diff.MAX_IMAGE_BYTES:
        raise ValueError("texture image read exceeds bound")
    return data, hashlib.sha256(data).hexdigest()


def compare(original: Path, modified: Path,
            texture_name: str, container_path: str | None) -> dict:
    if not texture_name or len(texture_name) > 240 or any(c in texture_name for c in "\r\n\x00"):
        raise ValueError("invalid texture name")
    old, old_sha = read(original)
    new, new_sha = read(modified)
    evidence = diff.image_diff(old, new)
    return {
        "schema": 1,
        "source": "externally_decoded_texture_pair",
        "original_exported_image": original.name,
        "modified_exported_image": modified.name,
        "original_export_sha256": old_sha,
        "modified_export_sha256": new_sha,
        "texture_name": texture_name,
        "source_container_path_hint": container_path,
        "container_original_sha256": None,
        "container_modified_sha256": None,
        "texture_bytes_in_original_container_verified": False,
        "buttons_and_scene_semantics": None,
        "game_update_and_title_qualified": False,
        "ps5_gameplay_qualified": False,
        "image_difference": evidence,
        "warning": "Only externally exported textures were compared. Source container identity, reimport correctness, mipmaps, and original game/update still need verification.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-image", required=True, type=Path)
    p.add_argument("--modified-image", required=True, type=Path)
    p.add_argument("--texture-name", required=True)
    p.add_argument("--container", help="RomFS-relative original Unity/BNTX/etc container path (unverified hint)")
    p.add_argument("--out", type=Path, help="new JSON report file")
    args = p.parse_args()
    try:
        if args.out and (args.out.exists() or args.out.is_symlink() or
                         not args.out.parent.is_dir() or args.out.parent.is_symlink()):
            raise ValueError("unsafe output file destination")
        report = json.dumps(compare(args.original_image, args.modified_image,
                                    args.texture_name, args.container), indent=2) + "\n"
        if args.out:
            args.out.write_text(report, encoding="utf-8")
            print(f"TEXTURE DIFF {args.out} (no game assets modified)")
        else:
            print(report, end="")
        return 0
    except (OSError, ValueError, diff.UnidentifiedImageError,
            diff.Image.DecompressionBombError) as exc:
        print(f"REJECTED texture pair: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
