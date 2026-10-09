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
import struct
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
scanner = load_module("eden_ps_glyph_scan", ROOT / "tools/ps-glyph-scan.py")
reuse = load_module("eden_ps_glyph_reuse", ROOT / "tools/ps-glyph-reuse.py")


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
                {"button": "cross", "rect": [4, 4, 52, 52]},
                {"button": "circle", "rect": [69, 4, 52, 52]},
            ],
        }],
    }
    spec = root / "map.json"

    def save_settings():
        spec.write_text(json.dumps(settings), "utf-8")

    save_settings()
    # Offline geometry-first discovery sees the two isolated button regions.
    # The user must *still* identify their semantics; no AI guess or
    # fabricated Cross/Circle mapping may enter the renderer automatically.
    # Synthetic Switch BNTX container: only the header/texture table/one
    # BRTI and UTF-8 name are materialized. Never decode or inject textures.
    # These are invented bytes, not actual game-owned artwork.
    nx_file = romfs / "UI" / "button_icons.bntx"
    nx = bytearray(0x300)
    nx[:8] = b"BNTX\0\0\0\0"
    nx[0x0C:0x0E] = b"\xff\xfe"
    nx[0x20:0x24] = b"NX  "
    struct.pack_into("<I", nx, 0x1C, len(nx))
    struct.pack_into("<I", nx, 0x24, 1)
    struct.pack_into("<Q", nx, 0x28, 0x80)
    struct.pack_into("<Q", nx, 0x80, 0xA0)
    nx[0xA0:0xA4] = b"BRTI"
    struct.pack_into("<H", nx, 0xA0 + 0x12, 1)  # linear mode
    struct.pack_into("<H", nx, 0xA0 + 0x16, 1)  # 1 mip
    struct.pack_into("<I", nx, 0xA0 + 0x1C, 0x0B01)  # RGBA8 UNORM
    struct.pack_into("<IIII", nx, 0xA0 + 0x24, 128, 64, 1, 1)
    struct.pack_into("<I", nx, 0xA0 + 0x50, 1024)
    nx[0xA0 + 0x5C] = 1  # 2D
    struct.pack_into("<Q", nx, 0xA0 + 0x60, 0x160)
    label = b"ui_button_cross"
    struct.pack_into("<H", nx, 0x160, len(label))
    nx[0x162:0x162 + len(label)] = label
    nx_file.write_bytes(nx)
    metadata = scanner.bntx.inspect(nx_file)
    assert metadata["texture_count"] == 1
    assert metadata["textures"][0]["name"] == "ui_button_cross"
    assert metadata["textures"][0]["format"] == "RGBA8"
    assert metadata["textures"][0]["width"] == 128
    assert metadata["textures"][0]["candidate_name"] is True
    assert metadata["textures"][0]["read_only"] is True

    proposals = scanner.scan(romfs)
    assert proposals["candidate_atlases"]
    assert len(proposals["bntx_containers"]) == 1
    assert proposals["bntx_containers"][0]["candidate_texture_count"] == 1
    proposed = proposals["candidate_atlases"][0]
    assert proposed["original_sha256"] == sha
    assert proposed["candidate_count"] == 2
    assert all(slot["button"] is None for slot in proposed["slots"])
    rects = [tuple(slot["rect"]) for slot in proposed["slots"]]
    assert not atlas.overlaps(rects[0], rects[1])
    assert all(x >= 0 and y >= 0 and w > 0 and h > 0 for x, y, w, h in rects)
    # No game bytes are changed by candidate extraction.
    assert hashlib.sha256(original.read_bytes()).hexdigest() == sha
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
    # Identical atlas bytes permit reusing geometry on another game, but
    # labels remain null unless semantics were explicitly approved.
    copied = reuse.suggest(spec, romfs, "0100C49025D3E000", "9.0.0")
    assert copied["title_id"] == "0100C49025D3E000"
    assert copied["atlases"][0]["slots"][0]["button"] is None
    approved = reuse.suggest(spec, romfs, "0100C49025D3E000", "9.0.0", True)
    assert approved["atlases"][0]["slots"][0]["button"] == "cross"
    draft = scanner.draft_spec(proposals, "01007EF00011E000", "1.0.0")
    assert draft["atlases"][0]["slots"][0]["button"] is None
    assert draft["schema"] == 1
    draft_file = root / "unapproved-draft.json"
    draft_file.write_text(json.dumps(draft), encoding="utf-8")
    must_reject(lambda: atlas.render(draft_file, romfs, icons, root / "unapproved-output"))
    assert scanner.alpha_candidates(Image.new("RGBA", (64, 64), (0, 0, 0, 0))) == []
    assert scanner.alpha_candidates(Image.new("RGBA", (64, 64), (10, 20, 30, 255))) == []
    assert next_catalogue["revision"] == merged["revision"] + 1

    # A malicious manifest must not sneak a traversal path into the native
    # catalogue even if its replacement bytes and hashes are valid.
    manifest_path = dest / "manifest.json"
    untouched_manifest = manifest_path.read_bytes()
    try:
        for unsafe in ("../UI/prompts.png", "UI/../prompts.png",
                       "/UI/prompts.png", "UI\\prompts.png", "UI//prompts.png", "UI\x00/prompts.png"):
            modified = json.loads(untouched_manifest)
            modified["files"][0]["romfs_path"] = unsafe
            manifest_path.write_text(json.dumps(modified), encoding="utf-8")
            must_reject(lambda: catalogue.build([dest]))
    finally:
        manifest_path.write_bytes(untouched_manifest)
    manifest = json.loads(untouched_manifest)
    duplicate = dict(manifest["files"][0])
    duplicate["romfs_path"] = duplicate["romfs_path"].swapcase()
    duplicate["replacement"] = "replacement/UI/other.png"
    manifest["files"].append(duplicate)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    must_reject(lambda: catalogue.build([dest]))
    manifest_path.write_bytes(untouched_manifest)
    assert catalogue.build([dest])["titles"] == merged["titles"]

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
    settings["atlases"][0]["slots"][1]["rect"] = [69, 4, 52, 52]
    # A slot can contain transparent pixels and STILL cut into its own
    # nontransparent glyph boundary. Reject it rather than overwriting HUD.
    settings["atlases"][0]["slots"][0]["rect"] = [8, 8, 48, 48]
    save_settings()
    must_reject(lambda: atlas.render(spec, romfs, icons, root / "edge-touch"))
    settings["atlases"][0]["slots"][0]["rect"] = [4, 4, 52, 52]
    settings["atlases"][0]["romfs_path"] = "UI/prompts.bntx"
    save_settings()
    must_reject(lambda: atlas.render(spec, romfs, icons, root / "bntx"))
    candidates = atlas.discover(romfs)
    png_candidates = [x for x in candidates if x["romfs_path"] == "UI/prompts.png"]
    assert len(png_candidates) == 1
    assert png_candidates[0]["original_sha256"] == sha
    # Corrupt header count/pointers must fail closed, not seek outside ROMFS.
    corrupted = bytearray(nx)
    struct.pack_into("<Q", corrupted, 0x80, len(corrupted) + 1)
    nx_file.write_bytes(corrupted)
    try:
        scanner.bntx.inspect(nx_file)
    except scanner.bntx.InvalidBntx:
        pass
    else:
        raise AssertionError("accepted out-of-file BRTI pointer")

print("HOST FIXTURE PASS: shared PS icons, read-only glyph candidates, source SHA, atlas conversion, catalogue merge")
print("Universal game coverage / PS5 visual correctness: NOT CLAIMED")
