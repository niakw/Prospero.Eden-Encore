#!/usr/bin/env python3
"""Full synthetic game archive -> approved glyph -> ASTC -> Yaz0/SARC chain."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# Reuse the already tested BNTX and SARC fixture builders; their module
# initialization also runs standalone synthetic layout tests.
fixtures = module("eden_astc_example_fixture", "check-ps-glyph-bntx-astc.py")
sarc = module("eden_sarc_example_fixture", "check-ps-glyph-botw-archive-diff.py")
automate = module("eden_full_ps5_glyph_assembler", "ps-glyph-botw-auto-pack.py")
stage = module("eden_botw_stage_test", "ps-glyph-botw-stage-pack.py")


def refuse(f, name):
    try:
        f()
    except (ValueError, automate.UnsafeGlyph,
            automate.archive.UnsafeRepack):
        return
    raise AssertionError(f"unsafe active BOTW patch accepted: {name}")


with tempfile.TemporaryDirectory(prefix="eden-independent-ps-asset-test-") as root:
    base = Path(root)
    raw_png = base / "switch-original.png"
    astc_file = base / "switch-original.astc"
    icon_zip = base / "synthetic-cc-art.zip"
    original = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    ImageDraw.Draw(original).rectangle((2, 2, 5, 5), fill=(255, 255, 255, 255))
    original.save(raw_png)
    automate.astc.run_astcenc("astcenc", ["-cl", str(raw_png), str(astc_file),
                                         "4x4", "-medium"])
    bntx = fixtures.fixture(astc_file.read_bytes(), 0, False)
    game_original = automate.archive.literal_yaz0(sarc.sarc(bntx))
    with zipfile.ZipFile(icon_zip, "w") as f:
        replacement = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(replacement)
        d.line((10, 10, 54, 54), fill=(255, 10, 10, 255), width=16)
        d.line((10, 54, 54, 10), fill=(255, 10, 10, 255), width=16)
        buff = io.BytesIO()
        replacement.save(buff, "PNG")
        f.writestr("PS5 Button Icons and Controls/Buttons Outline/White/128w/Cross.png",
                   buff.getvalue())

    manifest = {
        "schema": 1, "title_id": "01007EF00011E000",
        "update_version": "1.6.0", "profile": "playstation",
        "original_archive_sha256": hashlib.sha256(game_original).hexdigest(),
        "original_member_sha256": hashlib.sha256(bntx).hexdigest(),
        "member": "__Combined.bntx", "texture": "control_a_prompt",
        "scene": "world_interaction", "variant": "outline-white",
        "slots": [{"kind": "guest_action", "guest_button": "a",
                   "rect": [0, 0, 8, 8]}],
    }
    assembled, receipt = automate.assemble(game_original, manifest, icon_zip)
    assert receipt["glyph_profile"] == "playstation"
    assert receipt["approved_slots_count"] == 1
    assert receipt["bntx_astc"]["reencoded_astc_blocks"] == 4
    assert receipt["bntx_astc"]["untouched_astc_block_count"] == 12
    assert receipt["bntx_astc"]["untouched_encoded_blocks_preserved"]
    assert assembled != game_original
    old_sarc = automate.archive.botw.decode(game_original)
    new_sarc = automate.archive.botw.decode(assembled)
    assert len(old_sarc) == len(new_sarc)
    assert receipt["game_version_cryptographically_verified"] is False
    assert receipt["glyph_metadata_published_to_native_catalogue"] is False
    assert receipt["scene_and_update_confirmed_by_PS5_hardware"] is False

    source_member = bntx
    patched_member = new_sarc[-len(bntx):]
    assert len(source_member) == len(patched_member)
    old_image = automate.astc.decoded_image(source_member, "control_a_prompt")
    new_image = automate.astc.decoded_image(patched_member, "control_a_prompt")
    assert old_image.getpixel((3, 3)) != new_image.getpixel((3, 3))
    # On-console-compatible graphics NOT assumed from host tests.
    assert new_image.getpixel((12, 12)) == old_image.getpixel((12, 12))

    # Stage an installer-compatible, checksum-verified local LayeredFS
    # candidate from these synthetic game archives. Nothing gets installed.
    romfs = base / "original-romfs"
    original_resource = romfs / "Layout" / "Controller.sblarc"
    original_resource.parent.mkdir(parents=True)
    original_resource.write_bytes(game_original)
    modified_resource = base / "Controller-edited.sblarc"
    modified_resource.write_bytes(assembled)
    pack_root = base / "local-glyph-test-pack"
    candidate = stage.stage(romfs, modified_resource, receipt,
                            "Layout/Controller.sblarc", manifest["title_id"],
                            manifest["update_version"], pack_root)
    assert candidate == pack_root
    assert (pack_root / "replacement/Layout/Controller.sblarc").read_bytes() == assembled
    approved = stage.pack.verify(pack_root, romfs, manifest["title_id"])
    assert approved["files"][0]["romfs_path"] == "Layout/Controller.sblarc"
    refuse(lambda: stage.stage(romfs, modified_resource, receipt,
                               "Layout/Controller.sblarc", manifest["title_id"],
                               manifest["update_version"], pack_root),
           "overwriting existing local pack")

    wrong = dict(manifest, original_archive_sha256="0" * 64)
    refuse(lambda: automate.assemble(game_original, wrong, icon_zip),
           "wrong update archive")
    wrong = dict(manifest, profile="switch")
    refuse(lambda: automate.assemble(game_original, wrong, icon_zip),
           "Switch physical session mapped to PS artwork")
    wrong = dict(manifest, slots=[{"kind": "guest_action", "guest_button": "z",
                                  "rect": [0, 0, 8, 8]}])
    refuse(lambda: automate.assemble(game_original, wrong, icon_zip),
           "invented guest input name")
    wrong = dict(manifest, slots=[{"kind": "controller_position", "face": "right",
                                  "rect": [0, 0, 8, 8]}])
    refuse(lambda: automate.assemble(game_original, wrong, icon_zip),
           "missing different licensed Circle asset")

print("PASS: synthetic BOTW Switch Yaz0 SARC -> BNTX -> ASTC -> PS Cross graphic -> bounded Yaz0 resource")
print("PASS: independent icon ZIP, Cross=A semantics, source hashes, unmodified ASTC blocks and rejection gates")
print("No real Zelda files or compatible PS5 glyph pack were installed or published")
