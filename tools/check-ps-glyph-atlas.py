#!/usr/bin/env python3
"""Offline synthetic fixtures for shared PS icon atlas -> per-game RomFS packs.

Deliberately uses synthetic pixels, never Nintendo or licensed Zacksly images.
This script is to be executed only in an authorized test phase. It does not
require a console or write into a real game directory.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, source: Path):
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


atlas = load_module("eden_ps_glyph_atlas", ROOT / "tools/ps-glyph-atlas.py")
pack = load_module("eden_ps_glyph_pack", ROOT / "tools/ps-glyph-pack.py")
catalogue = load_module("eden_ps_glyph_catalogue", ROOT / "tools/ps-glyph-catalogue.py")


def must_reject(fn):
    try:
        fn()
    except (atlas.InvalidAtlas, catalogue.InvalidCatalogue, pack.InvalidPack):
        return
    raise AssertionError("invalid glyph conversion unexpectedly accepted")


def png_bytes(name: str):
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if name == "Cross":
        draw.line((25, 25, 103, 103), fill=(255, 255, 255, 255), width=6)
        draw.line((103, 25, 25, 103), fill=(255, 255, 255, 255), width=6)
    else:
        draw.ellipse((20, 20, 108, 108), outline=(255, 255, 255, 255), width=7)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


with tempfile.TemporaryDirectory(prefix="eden-ps-glyph-atlas-") as work:
    root = Path(work)
    romfs = root / "romfs"
    original = romfs / "UI" / "prompts.png"
    original.parent.mkdir(parents=True)
    image = Image.new("RGBA", (128, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.rectangle((8, 8, 52, 52), outline=(255, 255, 255, 255), width=5)
    d.rectangle((73, 8, 115, 52), outline=(255, 255, 255, 255), width=5)
    image.save(original)
    sha = hashlib.sha256(original.read_bytes()).hexdigest()

    icons = root / "synthetic-ps5-icons.zip"
    with zipfile.ZipFile(icons, "w") as z:
        for name in ("Cross", "Circle"):
            z.writestr(atlas.ROOT_MARKER + atlas.VARIANTS["outline-white"] +
                       name + ".png", png_bytes(name))

    settings = {
        "schema": 1, "title_id": "01007EF00011E000", "update_version": "1.0.0",
        "variant": "outline-white",
        "atlases": [{
            "romfs_path": "UI/prompts.png", "original_sha256": sha,
            "slots": [
                {"button": "cross", "rect": [8, 8, 48, 48]},
                {"button": "circle", "rect": [72, 8, 48, 48]},
            ],
        }],
    }
    spec = root / "map.json"

    def save_settings():
        spec.write_text(json.dumps(settings), "utf-8")

    save_settings()
    dest = root / "generated"
    atlas.render(spec, romfs, icons, dest)
    assert hashlib.sha256(original.read_bytes()).hexdigest() == sha
    replacement = dest / "replacement" / "UI" / "prompts.png"
    assert replacement.is_file()
    assert replacement.read_bytes() != original.read_bytes()
    with Image.open(replacement) as patched:
        assert patched.mode == "RGBA" and patched.size == (128, 64)
        assert patched.getpixel((0, 0))[3] == 0
    verified = pack.verify(dest, romfs, "01007EF00011E000")
    assert len(verified["files"]) == 1
    assert "Zacksly" in (dest / "ARTWORK_ATTRIBUTION.txt").read_text()
    mods = root / "mods"
    mods.mkdir()
    installed = pack.install(dest, romfs, mods, "01007EF00011E000")
    assert (installed / "ARTWORK_ATTRIBUTION.txt").exists()
    assert (installed / "romfs" / "UI" / "prompts.png").read_bytes() == replacement.read_bytes()

    merged = catalogue.build([dest])
    assert merged["revision"] > 2 and len(merged["titles"]) == 1
    existing = root / "existing.json"
    existing.write_text(json.dumps(merged), "utf-8")
    must_reject(lambda: catalogue.build([dest], existing))  # duplicate rule

    other = json.loads(json.dumps(settings))
    other["update_version"] = "1.0.1"
    other_spec = root / "other.json"
    other_spec.write_text(json.dumps(other), "utf-8")
    other_pack = root / "other-pack"
    atlas.render(other_spec, romfs, icons, other_pack)
    next_catalogue = catalogue.build([other_pack], existing)
    assert len(next_catalogue["titles"]) == 2
    assert next_catalogue["revision"] == merged["revision"] + 1

    # Reject tampering at every boundary, before exposing a fake compatibility.
    replacement.write_bytes(b"modified after glyph generation")
    must_reject(lambda: catalogue.build([dest]))
    must_reject(lambda: pack.verify(dest, romfs, "01007EF00011E000"))
    settings["atlases"][0]["original_sha256"] = "0" * 64
    save_settings()
    must_reject(lambda: atlas.render(spec, romfs, icons, root / "wrong-sha"))
    settings["atlases"][0]["original_sha256"] = sha
    settings["atlases"][0]["slots"][1]["rect"] = [20, 8, 48, 48]
    save_settings()
    must_reject(lambda: atlas.render(spec, romfs, icons, root / "overlap"))
    settings["atlases"][0]["slots"][1]["rect"] = [72, 8, 48, 48]
    settings["atlases"][0]["romfs_path"] = "UI/prompts.bntx"
    save_settings()
    must_reject(lambda: atlas.render(spec, romfs, icons, root / "bntx"))
    candidates = atlas.discover(romfs)
    assert candidates[0]["romfs_path"] == "UI/prompts.png"
    assert candidates[0]["original_sha256"] == sha

print("HOST FIXTURE PASS: shared PS icons to two atlas slots, source SHA, mod installer, rights, catalogue merge")
print("Universal game coverage / PS5 visual correctness: NOT CLAIMED")
