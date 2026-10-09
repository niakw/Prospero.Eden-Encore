#!/usr/bin/env python3
"""Synthetic ZIP-ROMFS original-versus-mod ASTC sprite position discovery."""
from __future__ import annotations

import importlib.util
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

TOOLS = Path(__file__).resolve().parent


def load(name: str, filename: str):
    s = importlib.util.spec_from_file_location(name, TOOLS / filename)
    assert s and s.loader
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


astc = load("eden_zip_astc_sample", "check-ps-glyph-bntx-astc.py")
sarc = load("eden_zip_sarc_sample", "check-ps-glyph-botw-archive-diff.py")
codec = load("eden_zip_astc_codec", "ps-glyph-bntx-astc.py")
archive = load("eden_zip_sarc_rebuild", "ps-glyph-botw-archive-repack.py")
zipscan = load("eden_zip_mod_scan", "ps-glyph-mod-zip-positions.py")

with tempfile.TemporaryDirectory(prefix="eden-source-mod-zip-") as base:
    root = Path(base)
    romfs = root / "original"
    (romfs / "Layout").mkdir(parents=True)
    png_original = root / "original.png"
    png_mod = root / "modded.png"
    astc_original = root / "orig.astc"
    astc_mod = root / "mod.astc"
    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((2, 2, 12, 12),
                                    fill=(220, 220, 220, 255))
    image.save(png_original)
    changed = image.copy()
    ImageDraw.Draw(changed).rectangle((6, 6, 9, 9),
                                      fill=(220, 30, 50, 255))
    changed.save(png_mod)
    for input_path, output in [(png_original, astc_original), (png_mod, astc_mod)]:
        codec.run_astcenc("astcenc",
                          ["-cl", str(input_path), str(output), "4x4", "-thorough"])

    bntx_original = astc.fixture(astc_original.read_bytes(), 0, False)
    bntx_modified = astc.fixture(astc_mod.read_bytes(), 0, False)
    raw_original = archive.literal_yaz0(sarc.sarc(bntx_original))
    raw_modified = archive.literal_yaz0(sarc.sarc(bntx_modified))
    (romfs / "Layout" / "Buttons.sblarc").write_bytes(raw_original)
    modzip = root / "BOTW_UI_WESTERN_TEST.zip"
    with zipfile.ZipFile(modzip, "w") as z:
        z.writestr("Western/Layout/romfs/Layout/Buttons.sblarc", raw_modified)
        z.writestr("Western/Layout/romfs/Layout/GameActor.sbactorpack", b"TEST")
    out = zipscan.gather(modzip, romfs, "world_interaction")
    assert out["scanned_romfs_entries"] == 2
    assert out["matched_native_ui_archives"] == 1, out
    assert out["glyph_position_candidates"] >= 1, out
    assert out["all_candidate_action_labels_unreviewed"]
    assert out["mod_binaries_redistributed"] is False
    assert len(out["unresolved"]) == 1
    assert out["unresolved"][0]["status"] == "different_resource_format_not_ignored"
    assert out["matched_archives"][0]["romfs_path"] == "Layout/Buttons.sblarc"
    detected = out["matched_archives"][0]["positions"]["textures"][0]
    assert detected["detected_original_switch_slots"]
    assert all(x["kind"] is None for x in detected["detected_original_switch_slots"])
    # Whole ZIP indexes do not infer active game support or change mod files.
    assert (romfs / "Layout" / "Buttons.sblarc").read_bytes() == raw_original
    # Full mod packs can carry >96 unrelated layout/language files.
    # Budget expensive SARC image decodes, never reject whole ZIP for that.
    expanded_zip = root / "large-ui-mod.zip"
    with zipfile.ZipFile(expanded_zip, "w") as z:
        for n in range(105):
            z.writestr(f"romfs/Message/Menu_{n:03d}.msbt", b"SYNTHETIC")
        z.writestr("romfs/Layout/Buttons.sblarc", raw_modified)
    expanded = zipscan.gather(expanded_zip, romfs, "world_interaction")
    assert expanded["scanned_romfs_entries"] == 106
    assert expanded["matched_native_ui_archives"] == 1
    assert expanded["glyph_position_candidates"] >= 1
    assert len(expanded["unresolved"]) == 105

    bad_zip = root / "modified-unmatched.zip"
    with zipfile.ZipFile(bad_zip, "w") as z:
        z.writestr("romfs/Layout/Missing.sblarc", raw_modified)
    bad = zipscan.gather(bad_zip, romfs, "world_interaction")
    assert bad["matched_native_ui_archives"] == 0
    assert bad["unresolved"][0]["status"] == "unmatched_or_unreadable"

print("PASS: mod ZIP auto-discovery yields real original Switch UI ASTC sprite XYWH from changed assets")
print("PASS: unknown archives reported, missing originals rejected, and no mod contents extracted/installed")
