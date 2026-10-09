#!/usr/bin/env python3
"""Check same-game UI placement reuse without assuming equal binary texture layouts."""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("eden_scene_coordinate_transfer",
                                              HERE / "ps-glyph-scene-positions.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def refuse(f, reason: str) -> None:
    try:
        f()
    except module.InvalidPosition:
        return
    raise AssertionError(f"accepted malformed same-game UI layout: {reason}")


dst = module.dont_starve_together()
assert dst["verified_from_source_code"]
assert dst["total_common_scene_anchors"] == 17
assert dst["exactly_reused_positions"] == 2
assert dst["positions"]["L2"]["same_position"]
assert dst["positions"]["R2"]["same_position"]
assert dst["positions"]["CROSS"]["same_position"] is False
assert dst["positions"]["CROSS"]["delta_switch_to_ps4_xy"] == [0, -45]
assert dst["romfs_atlas_rectangles"] is None
assert dst["screen_pixel_positions"] is None
assert dst["runtime_qualified"] is False

source = {
    "schema": 1,
    "game": "Synthetic Cross-Platform Game",
    "scene": "gameplay",
    "source_frame": {"x": 0, "y": 0, "width": 1920, "height": 1080},
    "target_frame": {"x": 0, "y": 0, "width": 1280, "height": 720},
    "anchors": [
        {"id": "interact_a", "x": 1440, "y": 810,
         "semantic": "guest_action", "source_proof": "https://example.com/real-code-line"},
        {"id": "controller_face_right", "x": 960, "y": 540,
         "semantic": "controller_position", "source_proof": "https://example.com/real-code-line"},
    ],
}
report = module.transfer(source)
assert report["anchors"][0]["target_scene_xy"] == [960, 540]
assert report["anchors"][0]["source_normalized_xy"] == [.75, .75]
assert report["anchors"][1]["target_scene_xy"] == [640, 360]
assert report["romfs_texture_slots"] is None
assert report["target_viewport_approved"] is False
assert report["active_in_emulator"] is False

resized = json.loads(json.dumps(source))
resized["target_frame"] = {"x": 100, "y": 200, "width": 2560, "height": 1440}
assert module.transfer(resized)["anchors"][0]["target_scene_xy"] == [2020, 1280]

bad = json.loads(json.dumps(source))
bad["anchors"][0]["x"] = -5
refuse(lambda: module.transfer(bad), "out-of-viewport coordinates")
bad = json.loads(json.dumps(source))
bad["anchors"][0]["x"] = float("nan")
refuse(lambda: module.transfer(bad), "NaN")
bad = json.loads(json.dumps(source))
bad["anchors"][1]["id"] = "interact_a"
refuse(lambda: module.transfer(bad), "duplicate IDs")
bad = json.loads(json.dumps(source))
bad["anchors"][1]["semantic"] = "texture_slot"
refuse(lambda: module.transfer(bad), "texture slots disguised as scene placements")
bad = json.loads(json.dumps(source))
bad["target_frame"]["width"] = 0
refuse(lambda: module.transfer(bad), "invalid target frame")
bad = json.loads(json.dumps(source))
bad["anchors"][0]["source_proof"] = ""
refuse(lambda: module.transfer(bad), "missing public/source provenance")

with tempfile.TemporaryDirectory() as tmp:
    file = Path(tmp) / "dst-normalized.json"
    file.write_text(json.dumps(report))
    assert module.document(file) == report

print("PASS: known same-game Switch/PlayStation Lua UI anchors and normalized viewport reflow")
print("PASS: source provenance, distinct scene/texture spaces and unverified scenes fail closed")
print("Host fixture only; BOTW exact atlas XYWH and console rendering NOT established.")
