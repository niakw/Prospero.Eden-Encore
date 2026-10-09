#!/usr/bin/env python3
"""Synthetic metadata correctness guard; no mod/game files and no PS5 execution.

Use only in an authorized future host test phase.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / file)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gate = module("eden_cross_gate", "check-ps-glyph-cross-platform-index.py")
coverage = module("eden_cross_coverage", "ps-glyph-platform-coverage.py")
switch = gate.read(gate.SWITCH_INDEX)
cross = gate.read(gate.CROSS_INDEX)
seeds = gate.read(gate.SEEDS_INDEX)
summary = gate.validate(cross, switch, seeds)
assert summary["cross_platform_sources"] == 22
assert summary["switch_games_referenced"] == 16
assert summary["switch1_seed_games"] == 10
assert summary["verified_switch_rectangles"] == 0

report = coverage.worklist(switch, cross, seeds)
assert report["games"] == 28
assert report["switch1_seed_only_games"] == 10
assert report["games_with_other_platform_leads"] == 16
assert report["verified_switch_atlas_rectangles"] == 0
assert all(item["requires_matching_game_romfs"] for item in report["worklist"])
assert all(item["requires_scene_semantics_and_native_ps5_test"] for item in report["worklist"])
assert {x["switch_title"] for x in report["worklist"]} == {
    item["title"] for item in switch["mods"]
} | {item["switch_game"] for item in seeds["games"]}


def must_reject(cross_data: dict):
    try:
        gate.validate(cross_data, switch, seeds)
    except ValueError:
        return
    raise AssertionError("bad cross-platform claim passed source-only evidence gate")


tamper = copy.deepcopy(cross)
tamper["sources"][0]["exact_switch_rect_xywh"] = [0, 0, 10, 10]
tamper["statistics"]["verified_cross_platform_pixel_rects"] = 1
must_reject(tamper)  # no original Switch SHA / runtime equivalence
tamper = copy.deepcopy(cross)
tamper["sources"][0]["switch_runtime_qualified"] = True
must_reject(tamper)
tamper = copy.deepcopy(cross)
tamper["sources"][0]["relationship"] = "unverified_same_bytes"
must_reject(tamper)
tamper = copy.deepcopy(cross)
tamper["sources"][0]["switch_game"] = "Unknown imaginary game"
must_reject(tamper)
tamper = copy.deepcopy(cross)
tamper["sources"][1]["id"] = tamper["sources"][0]["id"]
must_reject(tamper)

print("HOST FIXTURE PASS: 22 cross-platform leads, 16 matched Switch games, 28-title research worklist")
print("No binary atlas coordinates, mod-install permissions or PS5 operation implied")
