#!/usr/bin/env python3
"""Synthetic, local-only regression fixtures for ps-glyph-mod-diff.py.

Run only when tests are authorized; no Nintendo images and no mod archives
downloaded. Verifies coordinates, transparent alpha changes and rejection
of invalid ZIP members.
"""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("eden_mod_diff", ROOT / "tools/ps-glyph-mod-diff.py")
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
FOLDER_SPEC = importlib.util.spec_from_file_location(
    "eden_folder_mod_diff", ROOT / "tools/ps-glyph-mod-folder-diff.py")
assert FOLDER_SPEC is not None and FOLDER_SPEC.loader is not None
folder_module = importlib.util.module_from_spec(FOLDER_SPEC)
FOLDER_SPEC.loader.exec_module(folder_module)
TEXTURE_SPEC = importlib.util.spec_from_file_location(
    "eden_exported_texture_diff", ROOT / "tools/ps-glyph-exported-texture-diff.py")
assert TEXTURE_SPEC is not None and TEXTURE_SPEC.loader is not None
texture_module = importlib.util.module_from_spec(TEXTURE_SPEC)
TEXTURE_SPEC.loader.exec_module(texture_module)


def png(im: Image.Image) -> bytes:
    stream = io.BytesIO()
    im.save(stream, format="PNG")
    return stream.getvalue()


mask = Image.new("L", (8, 6), 0)
for pos in ((0, 0), (1, 1), (4, 1), (6, 1)):
    mask.putpixel(pos, 1)
boxes, pixels = module.connected_rects(mask)
assert pixels == 4
assert boxes == [[0, 0, 2, 2], [4, 1, 1, 1], [6, 1, 1, 1]], boxes

source = Image.new("RGBA", (48, 32), (0, 0, 0, 0))
d = ImageDraw.Draw(source)
d.rectangle((4, 4, 11, 11), fill=(255, 0, 0, 255))
d.rectangle((28, 5, 36, 13), fill=(0, 0, 255, 255))
revised = source.copy()
draw = ImageDraw.Draw(revised)
draw.rectangle((4, 4, 11, 11), fill=(0, 255, 0, 255))
draw.rectangle((28, 5, 36, 13), fill=(255, 255, 0, 255))
same = module.image_diff(png(source), png(source))
assert same["status"] == "pixel_identical" and same["changed_rects_xywh"] == []
changed = module.image_diff(png(source), png(revised))
assert changed["changed_pixels"] == 64 + 81
assert changed["changed_rects_xywh"] == [[4, 4, 8, 8], [28, 5, 9, 9]], changed
alpha = source.copy()
alpha.putpixel((1, 1), (0, 0, 0, 255))
assert module.image_diff(png(source), png(alpha))["changed_rects_xywh"] == [[1, 1, 1, 1]]
# Invisible RGB padding changes must not create false glyph rectangles.
hidden = source.copy()
hidden.putpixel((0, 0), (127, 99, 41, 0))
assert module.image_diff(png(source), png(hidden))["changed_rects_xywh"] == []
assert module.image_diff(png(source), png(Image.new("RGBA", (64, 32))))["status"] == "dimensions_changed"

with tempfile.TemporaryDirectory(prefix="eden-glyph-mod-diff-") as tmp:
    base = Path(tmp)
    romfs = base / "romfs"
    (romfs / "UI").mkdir(parents=True)
    (romfs / "UI" / "atlas.png").write_bytes(png(source))
    original_export = base / "original-Texture2D.png"
    modified_export = base / "patched-Texture2D.png"
    original_export.write_bytes(png(source))
    modified_export.write_bytes(png(revised))
    unity = texture_module.compare(original_export, modified_export,
                                   "controller_btns_outlined", "Data/resources.assets")
    assert unity["image_difference"]["changed_rects_xywh"] == [
        [4, 4, 8, 8], [28, 5, 9, 9]]
    assert unity["container_original_sha256"] is None
    assert unity["game_update_and_title_qualified"] is False
    archive = base / "ui-mod.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("PlayStationUI/romfs/UI/atlas.png", png(revised))
        z.writestr("PlayStationUI/romfs/UI/other.bntx", b"fake metadata")
    evidence = module.diff_mod(archive, romfs)
    relevant = {item["romfs_path"]: item for item in evidence["resources"]}
    assert relevant["UI/atlas.png"]["changed_rects_xywh"] == [[4, 4, 8, 8], [28, 5, 9, 9]]
    assert relevant["UI/atlas.png"]["original_sha256"]
    assert relevant["UI/atlas.png"]["replacement_sha256"]
    assert relevant["UI/other.bntx"]["status"] == "proprietary_or_other_format_unexamined"
    assert evidence["verified_title_update"] is None
    assert evidence["semantic_button_identity"] is None

    # Equivalent inspection for mods distributed as 7z/RAR and extracted by
    # an authorized user: reuse pixel geometry engine, never write to RomFS.
    unpacked = base / "unpacked-mod"
    (unpacked / "PS5" / "romfs" / "UI").mkdir(parents=True)
    (unpacked / "PS5" / "romfs" / "UI" / "atlas.png").write_bytes(png(revised))
    folder_evidence = folder_module.compare(unpacked, romfs)
    assert folder_evidence["source_kind"] == "already_extracted_mod_folder"
    assert folder_evidence["resources"][0]["changed_rects_xywh"] == [
        [4, 4, 8, 8], [28, 5, 9, 9]]
    bad_archive = base / "path-traversal.zip"
    with zipfile.ZipFile(bad_archive, "w") as z:
        z.writestr("romfs/../../escape.png", png(revised))
    try:
        module.diff_mod(bad_archive, romfs)
    except ValueError:
        pass
    else:
        raise AssertionError("ZIP traversal path passed fail-closed inventory")
    missing = base / "missing"
    missing.mkdir()
    missing_result = module.diff_mod(archive, missing)
    assert missing_result["resources"][0]["status"] == "unverified_or_unsupported"
    assert missing_result["resources"][0]["changed_rects_xywh"] is None

print("HOST FIXTURE PASS: exact pixel changes, independent regions, alpha, safe mod ZIP inventory")
print("Real title assets and PS5 game compatibility NOT tested")
