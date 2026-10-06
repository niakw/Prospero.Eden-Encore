#!/usr/bin/env python3
"""Validate a staged PPSA99008 artifact without requiring compile-directory metadata."""
from pathlib import Path
import json
import os
import sys

root = Path(__file__).resolve().parents[2]
app = Path(sys.argv[1] if len(sys.argv) > 1 else root / "build/release/PPSA99008").resolve()
assert app.name == "PPSA99008" and app.is_dir(), app

base = {
    "eboot.bin", "core-homebrew.nro", "sandbox-elevator.elf",
    "sce_module/libc.prx", "sce_sys/param.json", "sce_sys/icon0.png",
    "sce_sys/pic0.dds", "sce_sys/pic1.dds", "sce_sys/snd0.at9",
}
source_ui = root / "headless/prosperoeden/ui"
ui_expected = {
    "ui/" + p.relative_to(source_ui).as_posix()
    for p in source_ui.rglob("*") if p.is_file()
}
ui_expected.discard("ui/art/backdrop-blur.tga")
ui_expected.add("ui/art/backdrop.tga")
for source in (source_ui / "lang").glob("*.po"):
    ui_expected.add("ui/lang/" + source.with_suffix(".txt").name)
expected = base | ui_expected
actual = {p.relative_to(app).as_posix() for p in app.rglob("*") if p.is_file()}
missing = sorted(expected - actual)
extra = sorted(actual - expected)
assert not missing and not extra, f"package inventory mismatch missing={missing} extra={extra}"
for name in expected:
    p = app / name
    assert not p.is_symlink(), name
    assert p.stat().st_size > 0, name

param = json.loads((app / "sce_sys/param.json").read_text())
assert param["titleId"] == "PPSA99008"
assert param["contentId"].endswith("PROSPEROEDEN0001")
assert param["localizedParameters"]["en-US"]["titleName"] == "Prospero.Eden Encore"
assert (app / "sce_sys/icon0.png").read_bytes() == (root / "assets/icon0.png").read_bytes()
source_lang = sorted((source_ui / "lang").glob("*.po"))
staged_lang = sorted((app / "ui/lang").glob("*.po"))
assert len(source_lang) == 29, f"expected 29 launcher catalogs, got {len(source_lang)}"
assert [p.name for p in staged_lang] == [p.name for p in source_lang], "launcher catalog inventory differs"
assert any(p.name == "fr-FR.po" for p in staged_lang), "fr-FR launcher catalog missing"
for source in source_lang:
    staged = app / "ui/lang" / source.name
    companion = app / "ui/lang" / source.with_suffix(".txt").name
    assert staged.read_bytes() == source.read_bytes(), f"stale/corrupt launcher catalog: {source.name}"
    assert companion.read_bytes() == source.read_bytes(), f"stale/corrupt launcher catalog companion: {companion.name}"
assert (app / "sandbox-elevator.elf").stat().st_size > 0
assert (app / "eboot.bin").stat().st_size > 1024 * 1024
print(f"Staged Encore artifact PASS ({len(actual)} files)")
