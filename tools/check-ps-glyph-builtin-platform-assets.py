#!/usr/bin/env python3
"""Offline synthetic fixture for built-in cross-platform glyph-name discovery.

No Nintendo assets, no internet and no PS5 binaries. Run only when host
test execution is authorized.
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "eden_builtin_platform_art", ROOT / "tools/ps-glyph-builtin-platform-assets.py")
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

assert m.classify("UI/buttons_ps5.png")[0] == "playstation"
assert m.classify("UI/buttons_switch.png")[0] == "nintendo"
assert m.classify("UI/buttons_xbox.png")[0] == "xbox"
assert m.classify("UI/oops.png") == (None, None)
assert m.classify("ui/ps5_character_model.bin") == (None, None)

with tempfile.TemporaryDirectory(prefix="eden-builtin-prompt-") as tmp:
    root = Path(tmp)
    ui = root / "UI"
    ui.mkdir()
    for filename in ("controller_buttons_ps4.png", "controller_buttons_switch.png",
                     "controller_buttons_xbox.png", "ambient_ps4_texture.dds",
                     "generic_button.png"):
        (ui / filename).write_bytes(b"synthetic")
    report = m.discover(root)
    assert report["inspected_files"] == 5
    groups = report["multiplatform_name_families"]
    assert len(groups) == 1, groups
    assert set(groups[0]["platform_asset_name_candidates"]) == {
        "playstation", "nintendo", "xbox"}
    assert groups[0]["asset_bytes_compared"] is False
    assert report["verified_same_texture_geometry"] == 0

print("HOST FIXTURE PASS: exact controller art platform tokens and false-positive rejection")
print("No actual Switch platform art is verified by source filename alone")
