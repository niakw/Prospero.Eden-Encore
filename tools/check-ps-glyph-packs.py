#!/usr/bin/env python3
"""Offline security/compatibility tests for original in-game glyph RomFS packs.

No Nintendo/PlayStation game assets are read; all files are synthetic bytes.
Does NOT claim any real title's glyphs are supported or translated.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tools" / "ps-glyph-pack.py"
spec = importlib.util.spec_from_file_location("eden_ps_glyph_pack", GATE)
assert spec is not None and spec.loader is not None
import types
gate = types.ModuleType(spec.name)
spec.loader.exec_module(gate)

TITLE = "01007EF00011E000"
UPDATE_VERSION = "v1.2.0"
GAMEFILE = "UI/Shared/controller_prompt.bntx"
SOURCE_FILE = "replacement/dual-sense.bntx"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def rejected(fn, message: str) -> None:
    try:
        fn()
    except gate.InvalidPack:
        return
    raise AssertionError("invalid glyph pack accepted: " + message)


with tempfile.TemporaryDirectory(prefix="eden-glyph-packs-host-") as folder:
    root = Path(folder)
    source = root / "original-romfs"
    pack = root / "pack"
    mods = root / "mods"
    source.mkdir()
    pack.mkdir()
    mods.mkdir()
    original = b"original Nintendo A/B/X/Y atlas (synthetic fixture)"
    replacement = b"changed PlayStation circle/cross/square/triangle atlas (synthetic fixture)"
    write(source / GAMEFILE, original)
    write(pack / SOURCE_FILE, replacement)
    manifest = {
        "schema": 2,
        "title_id": TITLE,
        "update_version": UPDATE_VERSION,
        "rights": "User-created replacement artwork under explicit permission",
        "files": [{
            "romfs_path": GAMEFILE,
            "replacement": SOURCE_FILE,
            "original_sha256": digest(original),
            "replacement_sha256": digest(replacement),
        }],
    }

    def store(document: dict) -> None:
        (pack / "manifest.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    store(manifest)
    verified = gate.verify(pack, source, TITLE)
    assert verified["title_id"] == TITLE and len(verified["files"]) == 1

    rejected(lambda: gate.verify(pack, source, "0100FFFFFFFF0000"), "another game")
    rejected(lambda: gate.verify(pack, source, "WRONG"), "invalid title ID")

    bad = json.loads(json.dumps(manifest))
    bad["files"][0]["romfs_path"] = "../outside/file.bntx"
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE), "directory traversal")
    bad["files"][0]["romfs_path"] = "/outside/file.bntx"
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE), "absolute path")
    bad["files"][0]["romfs_path"] = "C:\\evil\\file.bntx"
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE), "windows path")

    bad = json.loads(json.dumps(manifest))
    bad["update_version"] = "../unsafe"
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE), "invalid update version")
    store(manifest)
    (pack / "manifest.json").write_text('{"schema": 2, "schema": 2}', encoding="utf-8")
    rejected(lambda: gate.verify(pack, source, TITLE), "duplicate JSON keys")
    store(manifest)
    bad = json.loads(json.dumps(manifest))
    bad["files"][0]["replacement_sha256"] = "0" * 64
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE), "tampered replacement")
    store(manifest)
    write(source / GAMEFILE, b"updated version: asset no longer matches")
    rejected(lambda: gate.verify(pack, source, TITLE), "updated or patched original asset")
    write(source / GAMEFILE, original)

    bad = json.loads(json.dumps(manifest))
    bad["files"].append(dict(bad["files"][0]))
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE), "duplicate game resource")
    bad["files"][1]["romfs_path"] = GAMEFILE.swapcase()
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE), "case collision")
    bad = json.loads(json.dumps(manifest))
    bad["rights"] = ""
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE), "no art redistribution rights")
    bad = json.loads(json.dumps(manifest))
    bad["files"][0]["replacement_sha256"] = bad["files"][0]["original_sha256"]
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE), "unchanged art")

    store(manifest)
    # A malicious mod pack must never redirect reads out of its own tree.
    (pack / SOURCE_FILE).unlink()
    (pack / SOURCE_FILE).symlink_to(source / GAMEFILE)
    rejected(lambda: gate.verify(pack, source, TITLE), "replacement symlink")
    (pack / SOURCE_FILE).unlink()
    write(pack / SOURCE_FILE, replacement)

    result = gate.install(pack, source, mods, TITLE)
    assert result == mods / TITLE / gate.MOD_NAME
    assert (result / "romfs" / GAMEFILE).read_bytes() == replacement
    assert (source / GAMEFILE).read_bytes() == original
    assert (result / "eden-glyph-pack.json").is_file()
    assert not (result / "romfs" / "eden-glyph-pack.json").exists()
    assert json.loads((result / "eden-glyph-pack.json").read_text())["update_version"] == UPDATE_VERSION
    assert sorted(f.name for f in (mods / TITLE).iterdir()) == [gate.MOD_NAME]
    rejected(lambda: gate.install(pack, source, mods, TITLE), "silent overwrite")
    assert (result / "romfs" / GAMEFILE).read_bytes() == replacement

    # Eden itself resolves mods/<TITLE> case-insensitively. Preserve an
    # existing lowercase directory rather than creating a second mod tree.
    lowercase_mods = root / "mods-lowercase"
    lowercase_mods.mkdir()
    lowercase_game = lowercase_mods / TITLE.lower()
    lowercase_game.mkdir()
    lowercase_result = gate.install(pack, source, lowercase_mods, TITLE)
    assert lowercase_result.parent == lowercase_game
    assert not (lowercase_mods / TITLE).exists()
    assert (lowercase_result / "romfs" / GAMEFILE).read_bytes() == replacement

    # Conflicting case variants are ambiguous to the actual game mod loader.
    conflicting = root / "mods-conflicting"
    conflicting.mkdir()
    (conflicting / TITLE.lower()).mkdir()
    (conflicting / TITLE).mkdir()
    rejected(lambda: gate.install(pack, source, conflicting, TITLE),
             "two case-colliding game title folders")

    # Even an incorrectly capitalized pre-existing glyph mod is never
    # silently overwritten.
    conflicting_child = root / "mods-colliding-glyph"
    conflicting_child.mkdir()
    game_folder = conflicting_child / TITLE
    game_folder.mkdir()
    (game_folder / gate.MOD_NAME.lower()).mkdir()
    rejected(lambda: gate.install(pack, source, conflicting_child, TITLE),
             "existing glyph mod with different capitalization")

    cmd = [sys.executable, "-B", str(GATE), "verify", "--pack", str(pack),
           "--original-romfs", str(source), "--title-id", TITLE]
    process = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "VERIFIED" in process.stdout
    process = subprocess.run(cmd[:-1] + ["BAD"], capture_output=True, text=True)
    assert process.returncode != 0 and "REJECTED" in process.stderr

    # Correctness integration: existing Eden loader already uses this exact
    # mods/<TITLE>/<name>/romfs tree with per-title mod enable/disable.
    mods_h = (ROOT / "headless" / "mods.h").read_text()
    main = (ROOT / "headless" / "main.cpp").read_text()
    assert 'name == "romfs" || name == "romfslite" || name == "romfs_ext"' in mods_h
    assert 'Eden::Mods::List(Eden::AssetsPath("mods"), title)' in main
    assert 'Settings::values.disabled_addons[title] = mods_off' in main

print("PASS legal PS glyph pack manifest: verified title/update/original+replacement SHA256, LayeredFS install, atomic stage, refusal/rollback")
print("IN-GAME artwork support: requires legitimate per-title resources and console version and active original graphic fingerprint qualification")
