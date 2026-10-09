#!/usr/bin/env python3
"""End-to-end OFFLINE original-authorized BOTW Switch PS-button glyph assembly.

Inputs: exact original BOTW Switch Yaz0/SARC file, metadata and sprite
rectangles approved for this version/scene, the user's licensed Zacksly
PS5 button PNG ZIP. Outputs a staged same-path Yaz0/SARC file and a
non-installation evidence report. No foreign Wii U/PC mod bytes copied.
Only altered ASTC 16-byte blocks of the named BNTX texture are patched;
every other SARC member and encoded ASTC block remains bit-identical.

This does NOT change the native glyph catalogue or automatically inject
game mods. Exact ROMFS source and physical PS5 screenshot proof required.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent


class UnsafeGlyph(ValueError):
    pass


def valid(cond, why):
    if not cond:
        raise UnsafeGlyph(why)


def load(name: str, script: str):
    sp = importlib.util.spec_from_file_location(name, ROOT / script)
    valid(sp is not None and sp.loader is not None, "missing required glyph tool")
    module = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(module)
    return module


archive = load("eden_glyph_archive_assemble", "ps-glyph-botw-archive-repack.py")
icons = load("eden_glyph_original_icons", "ps-glyph-atlas.py")
reconstruct = load("eden_glyph_button_semantics", "ps-glyph-reconstruct.py")
astc = archive.astc


def assemble(source: bytes, manifest: dict, icon_zip: Path,
             astcenc: str = "astcenc") -> tuple[bytes, dict]:
    expected = {"schema", "title_id", "update_version", "profile",
                "original_archive_sha256", "original_member_sha256",
                "member", "texture", "scene", "variant", "slots"}
    valid(isinstance(manifest, dict) and set(manifest) == expected and
          type(manifest["schema"]) is int and manifest["schema"] == 1,
          "complete, exact glyph assembly spec schema required")
    valid(manifest["profile"] == "playstation",
          "Eden PS-action texture gate allows fixed A=Cross session only")
    valid(manifest["variant"] in icons.VARIANTS,
          "missing licensed controller artwork variant")
    valid(isinstance(manifest["slots"], list) and
          0 < len(manifest["slots"]) <= 256, "approved sprite list required")
    valid(isinstance(icon_zip, Path) and icon_zip.is_file() and
          not icon_zip.is_symlink(), "licensed icon ZIP missing or unsafe")
    valid(hashlib.sha256(source).hexdigest() == manifest["original_archive_sha256"],
          "wrong original BOTW game resource SHA")
    original_sarc = (archive.botw.decode(source) if source.startswith(b"Yaz0")
                     else source)
    table = archive.botw.sarc.inventory_bytes(original_sarc)
    members = [x for x in table["members"] if x["name"] == manifest["member"]]
    valid(len(members) == 1, "named BNTX member absent")
    member = members[0]
    inner = original_sarc[member["content_offset"]:
                          member["content_offset"] + member["content_bytes"]]
    valid(hashlib.sha256(inner).hexdigest() == manifest["original_member_sha256"],
          "wrong version of original BNTX member")
    picture = astc.decoded_image(inner, manifest["texture"], astcenc)
    rects = []
    for slot in manifest["slots"]:
        valid(isinstance(slot, dict) and
              set(slot) == ({"kind", "guest_button", "rect"} if
                            slot.get("kind") == "guest_action" else
                            {"kind", "face", "rect"}),
              "explicit action or physical-controller position required")
        glyph = reconstruct.glyph_for_slot(slot, manifest["profile"])
        valid(glyph in icons.ICONS, "unknown PlayStation button icon")
        rects.append(slot["rect"])
    checked = astc.verify_rects(rects, *picture.size)
    edited = picture.copy()
    with zipfile.ZipFile(icon_zip) as source_zip:
        for slot, (x, y, w, h) in zip(manifest["slots"], checked):
            # Clear only an alpha-isolated source sprite; refuse overlay
            # over non-transparent unrelated UI backgrounds/label art.
            old = picture.crop((x, y, x + w, y + h))
            alpha = old.getchannel("A")
            box = alpha.getbbox()
            valid(box and box[0] > 0 and box[1] > 0 and
                  box[2] < w and box[3] < h,
                  "original Switch sprite not independently isolated in rectangle")
            glyph = reconstruct.glyph_for_slot(slot, manifest["profile"])
            graphic = icons.read_icon(source_zip, manifest["variant"], glyph)
            sprite = ImageOps.contain(graphic, (w - 2, h - 2),
                                      Image.Resampling.LANCZOS)
            cell = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            cell.alpha_composite(sprite, ((w - sprite.width) // 2,
                                          (h - sprite.height) // 2))
            edited.paste(cell, (x, y))
    plan = {
        "schema": 1,
        "title_id": manifest["title_id"],
        "update_version": manifest["update_version"],
        "original_archive_sha256": manifest["original_archive_sha256"],
        "original_member_sha256": manifest["original_member_sha256"],
        "member": manifest["member"], "texture": manifest["texture"],
        "scene": manifest["scene"], "rectangles": rects,
    }
    result, receipt = archive.build(source, plan, edited, astcenc)
    valid(result != source and len(result) <= archive.MAX_ARCHIVE_OUT,
          "artwork did not modify bounded output resource")
    receipt.update({
        "source_graphic_icon_zip_sha256": hashlib.sha256(icon_zip.read_bytes()).hexdigest()
            if icon_zip.stat().st_size <= 32 * 1024 * 1024 else None,
        "glyph_profile": "playstation", "glyph_variant": manifest["variant"],
        "approved_slots_count": len(rects),
        "scene_and_update_confirmed_by_PS5_hardware": False,
        "glyph_metadata_published_to_native_catalogue": False,
        "game_owned_graphics_not_licensed_for_public_redistribution": True,
    })
    return result, receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original", required=True, type=Path)
    p.add_argument("--spec", required=True, type=Path)
    p.add_argument("--icons-zip", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--report", required=True, type=Path)
    p.add_argument("--astcenc", default="astcenc")
    a = p.parse_args()
    try:
        for v in (a.original, a.spec, a.icons_zip):
            valid(v.is_file() and not v.is_symlink(), "missing/unsafe input file")
        valid(a.original.stat().st_size <= archive.botw.MAX_INPUT and
              a.spec.stat().st_size <= 128 * 1024,
              "oversized original/spec")
        for output in (a.out, a.report):
            valid(not output.exists() and not output.is_symlink() and
                  output.parent.is_dir() and not output.parent.is_symlink(),
                  "output already exists or parent unsafe")
        doc = json.loads(a.spec.read_text("utf-8"))
        result, evidence = assemble(a.original.read_bytes(), doc,
                                    a.icons_zip, a.astcenc)
        a.out.write_bytes(result)
        a.report.write_text(json.dumps(evidence, indent=2) + "\n")
        print(f"STAGED original-hash-bound glyph resource {a.out}")
        print("NOT activated in Eden; no on-console UI compatibility proof")
        return 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile,
            archive.UnsafeRepack, archive.botw.InvalidYaz0,
            archive.botw.sarc.InvalidSarc, astc.UnsafeAstc,
            astc.tile.InvalidTexture, icons.InvalidAtlas) as exc:
        print(f"REJECTED offline PlayStation glyph assembly: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
