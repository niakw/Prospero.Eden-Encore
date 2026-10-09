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
