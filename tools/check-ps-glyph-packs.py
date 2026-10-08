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
BUILD = "0123456789ABCDEF" * 2 + "01234567"
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
        "schema": 1,
        "title_id": TITLE,
        "build_id": BUILD,
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
    verified = gate.verify(pack, source, TITLE, BUILD)
    assert verified["title_id"] == TITLE and len(verified["files"]) == 1

    rejected(lambda: gate.verify(pack, source, "0100FFFFFFFF0000", BUILD), "another game")
    rejected(lambda: gate.verify(pack, source, TITLE, "A" * 40), "different game build")
    rejected(lambda: gate.verify(pack, source, TITLE, "BAD"), "invalid build ID")
    rejected(lambda: gate.verify(pack, source, "WRONG", BUILD), "invalid title ID")

    bad = json.loads(json.dumps(manifest))
    bad["files"][0]["romfs_path"] = "../outside/file.bntx"
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "directory traversal")
    bad["files"][0]["romfs_path"] = "/outside/file.bntx"
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "absolute path")
    bad["files"][0]["romfs_path"] = "C:\\evil\\file.bntx"
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "windows path")

    store(manifest)
    (pack / "manifest.json").write_text('{"schema": 1, "schema": 1}', encoding="utf-8")
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "duplicate JSON keys")
    store(manifest)
    bad = json.loads(json.dumps(manifest))
    bad["files"][0]["replacement_sha256"] = "0" * 64
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "tampered replacement")
    store(manifest)
    write(source / GAMEFILE, b"updated version: asset no longer matches")
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "updated or patched original asset")
    write(source / GAMEFILE, original)

    bad = json.loads(json.dumps(manifest))
    bad["files"].append(dict(bad["files"][0]))
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "duplicate game resource")
    bad["files"][1]["romfs_path"] = GAMEFILE.swapcase()
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "case collision")
    bad = json.loads(json.dumps(manifest))
    bad["rights"] = ""
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "no art redistribution rights")
    bad = json.loads(json.dumps(manifest))
    bad["files"][0]["replacement_sha256"] = bad["files"][0]["original_sha256"]
    store(bad)
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "unchanged art")

    store(manifest)
    # A malicious mod pack must never redirect reads out of its own tree.
    (pack / SOURCE_FILE).unlink()
    (pack / SOURCE_FILE).symlink_to(source / GAMEFILE)
    rejected(lambda: gate.verify(pack, source, TITLE, BUILD), "replacement symlink")
    (pack / SOURCE_FILE).unlink()
    write(pack / SOURCE_FILE, replacement)

    result = gate.install(pack, source, mods, TITLE, BUILD)
    assert result == mods / TITLE / gate.MOD_NAME
    assert (result / "romfs" / GAMEFILE).read_bytes() == replacement
    assert (source / GAMEFILE).read_bytes() == original
    assert (result / "eden-glyph-pack.json").is_file()
    assert not (result / "romfs" / "eden-glyph-pack.json").exists()
    assert json.loads((result / "eden-glyph-pack.json").read_text())["build_id"] == BUILD
    assert sorted(f.name for f in (mods / TITLE).iterdir()) == [gate.MOD_NAME]
    rejected(lambda: gate.install(pack, source, mods, TITLE, BUILD), "silent overwrite")
    assert (result / "romfs" / GAMEFILE).read_bytes() == replacement

    cmd = [sys.executable, "-B", str(GATE), "verify", "--pack", str(pack),
           "--original-romfs", str(source), "--title-id", TITLE, "--build-id", BUILD]
    process = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "VERIFIED" in process.stdout
    process = subprocess.run(cmd[:-1] + ["B" * 40], capture_output=True, text=True)
    assert process.returncode != 0 and "REJECTED" in process.stderr

    # Correctness integration: existing Eden loader already uses this exact
    # mods/<TITLE>/<name>/romfs tree with per-title mod enable/disable.
    mods_h = (ROOT / "headless" / "mods.h").read_text()
    main = (ROOT / "headless" / "main.cpp").read_text()
    assert 'name == "romfs" || name == "romfslite" || name == "romfs_ext"' in mods_h
    assert 'Eden::Mods::List(Eden::AssetsPath("mods"), title)' in main
    assert 'Settings::values.disabled_addons[title] = mods_off' in main

print("PASS legal PS glyph pack manifest: verified title/build/original+replacement SHA256, LayeredFS install, atomic stage, refusal/rollback")
print("IN-GAME artwork support: requires legitimate per-title resources and on-console title/build verification")
