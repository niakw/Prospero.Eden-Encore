#!/usr/bin/env python3
"""Synthetic metadata-only test fixture for Switch 1 base Title ID matching.

No real Nintendo game assets or external database copies included.
Not executed under the user's no-run gate.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "eden_switch1_titledb_resolver", ROOT / "tools/ps-glyph-switch1-titledb.py")
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

tid1 = "0100" + "123456789" + "000"
tid2 = "0100" + "223456789" + "000"
tid3 = "0100" + "323456789" + "000"
tid4 = "0100" + "423456789" + "000"
assert len(tid1) == 16
assert m.is_switch1_base(tid1)
assert not m.is_switch1_base("0400" + "123456789" + "000")  # Switch 2
assert not m.is_switch1_base("0100" + "123456789" + "800")  # update ID

sample = [
    {"title_id": tid1, "name": "Sonic Mania"},
    {"title_id": tid2, "name": "Sonic Mania"},
    {"titleId": tid3, "name": "Stardew Valley"},
    {"title_id": tid4, "description": "Another Game"},
    {"title_id": tid4, "name": "Another Game"},  # duplicate region
    {"title_id": "0400" + "123456789" + "000", "name": "Not Switch1"},
]
switch = {"mods":[{"title":"Sonic Mania"}]}
seeds = {"games":[{"switch_game":"Stardew Valley"}]}
out = m.resolve(sample, "a" * 64, switch, seeds, True)
entries = {x["requested_switch_game"]:x for x in out["researched_titles"]}
assert out["research_title_count"] == 2
assert entries["Sonic Mania"]["status"] == "ambiguous_multiple_title_ids"
assert entries["Sonic Mania"]["candidate_title_id"] is None
assert entries["Stardew Valley"]["status"] == "unique_name_candidate"
assert entries["Stardew Valley"]["candidate_title_id"] == tid3
assert not entries["Stardew Valley"]["glyph_art_compatible"]
assert len(out["all_switch1_base_title_candidates"]) == 4  # duplicate region dedup
assert all(not item["glyph_art_compatible"]
           for item in out["all_switch1_base_title_candidates"])

region_map = {"12345":{"id":tid3, "name":"Stardew Valley"},
              "12346":{"id":tid3, "name":"Stardew Valley"}}
assert len(list(m.entries(region_map))) == 2
assert m.clean_name("  SONIC MANIA!!  ") == m.clean_name("Sonic Mania")
print("HOST FIXTURE PASS: Switch 1 ID shape, regional dedup, ambiguous/name gating")
print("Not proof of actual installed game Title IDs, updates or in-game PlayStation glyphs")
