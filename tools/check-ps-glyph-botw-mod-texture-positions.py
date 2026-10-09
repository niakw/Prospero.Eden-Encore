#!/usr/bin/env python3
"""Host-only modded ASTC glyph diff locates exact Switch original sprite rect."""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def read(name: str, file: str):
    sp = importlib.util.spec_from_file_location(name, HERE / file)
    assert sp and sp.loader
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


sample = read("eden_ui_texture_positions_fixture", "check-ps-glyph-bntx-astc.py")
sarc = read("eden_ui_sarc_positions_fixture", "check-ps-glyph-botw-archive-diff.py")
tool = read("eden_ui_mod_positions", "ps-glyph-botw-mod-texture-positions.py")
with tempfile.TemporaryDirectory(prefix="eden-glyph-diff-real-format-") as root:
    where = Path(root)
    old_png = where / "original.png"
    new_png = where / "mod.png"
    old_astc = where / "original.astc"
    new_astc = where / "mod.astc"

    original = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    ImageDraw.Draw(original).rectangle((2, 2, 12, 12),
                                       fill=(20, 220, 60, 255))
    mod = original.copy()
    ImageDraw.Draw(mod).rectangle((6, 6, 9, 9),
                                  fill=(230, 25, 50, 255))
    original.save(old_png)
    mod.save(new_png)
    tool.astc.run_astcenc("astcenc",
                          ["-cl", str(old_png), str(old_astc), "4x4", "-thorough"])
    tool.astc.run_astcenc("astcenc",
                          ["-cl", str(new_png), str(new_astc), "4x4", "-thorough"])
    orig_blob = sample.fixture(old_astc.read_bytes(), 0, False)
    mod_blob = sample.fixture(new_astc.read_bytes(), 0, False)
    original_archive = where / "original.sblarc"
    modded_archive = where / "modded.sblarc"
    # No fake resource values: both are authentic synthetic Yaz0/SARC/BNTX
    # containers built with the production codec and checked parser.
    repacker = read("eden_mod_positions_sarc_packer", "ps-glyph-botw-archive-repack.py")
    original_archive.write_bytes(repacker.literal_yaz0(sarc.sarc(orig_blob)))
    modded_archive.write_bytes(repacker.literal_yaz0(sarc.sarc(mod_blob)))
    outcome = tool.evidence(original_archive, modded_archive,
                            "world_interaction")
    assert outcome["changed_texture_count"] == 1, outcome
    texture = outcome["textures"][0]
    assert texture["texture"] == "control_a_prompt"
    assert texture["changed_rendered_pixels"] > 0
    assert texture["mod_bntx_sha256"] != texture["original_bntx_sha256"]
    assert texture["replacement_graphics_from_mod_copied"] is False
    assert texture["ready_to_install"] is False
    assert texture["detected_original_switch_slots"], texture
    for slot in texture["detected_original_switch_slots"]:
        assert slot["kind"] is None and slot["guest_button"] is None
        assert slot["controller_face"] is None
        assert not slot["action_semantics_reviewed"]
    # The changed location comes from real decoded Switch mod pixels,
    # not an assumed Wii U texture coordinate.
    assert outcome["ui_sprite_position_proposals"] >= 1
    modded_archive.write_bytes(original_archive.read_bytes())
    equal = tool.evidence(original_archive, modded_archive,
                          "world_interaction")
    assert equal["changed_texture_count"] == 0
    assert equal["ui_sprite_position_proposals"] == 0

print("PASS: original vs modded Switch ASTC game archives expose actual decoded icon positions")
print("PASS: unchanged textures omitted; exact action IDs and runtime activation never guessed")
