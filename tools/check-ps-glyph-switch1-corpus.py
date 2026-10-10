#!/usr/bin/env python3
"""Scope gate: Switch1 base IDs, dual-release games, not Switch2-only IDs.

Count Title IDs as candidate catalog entries; never claim each corresponds
to an independently released commercial game. Same-game Switch 2 Editions
do not hide the underlying playable Switch 1 software.
"""
from __future__ import annotations
import importlib.util
import json
import tempfile
from pathlib import Path

source=Path(__file__).with_name("ps-glyph-switch1-corpus.py")
spec=importlib.util.spec_from_file_location("eden_test_switch1_scope",source)
assert spec and spec.loader
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

cases={
  "0": {"id":"01007EF00011E000",
        "name":"The Legend of Zelda: Breath of the Wild",
        "platform":"Nintendo Switch", "has_switch2_edition":True},
  "1": {"id":"04007EF00011E000",
        "name":"The Legend of Zelda: Breath of the Wild - Switch 2 Edition",
        "platform":"Nintendo Switch 2"},
  "2": {"id":"0400C3F00006E000",
        "name":"Mario Kart World", "platform":"Nintendo Switch 2"},
  "3": {"id":"0100000000010000",
        "name":"Super Mario Odyssey", "platform":"Nintendo Switch"},
  "4": {"id":"0100000000010800",
        "name":"Super Mario Odyssey Software Update",
        "platform":"Nintendo Switch"},
  "5": {"id":"01007EF00011E000",
        "name":"Zelda no Densetsu: Breath of the Wild",
        "platform":"Nintendo Switch"},
}
with tempfile.TemporaryDirectory(prefix="eden-switch1-only-") as temp:
    p=Path(temp)/"region1.json"
    q=Path(temp)/"region2.json"
    p.write_text(json.dumps({k:v for k,v in cases.items() if k!="5"}))
    q.write_text(json.dumps({"5":cases["5"]}))
    output=tool.merge([p,q],["The Legend of Zelda: Breath of the Wild"])
    assert output["game_count"]==2,output
    ids={x["title_id"] for x in output["games"]}
    assert ids=={"01007EF00011E000","0100000000010000"}
    assert not any(x.startswith("0400") for x in ids)
    zelda=next(x for x in output["games"]
               if x["title_id"]=="01007EF00011E000")
    assert zelda["previously_researched_title"]
    assert len(zelda["aliases"])==2
    assert output["scope"]=="switch1_metadata_all_supplied_regions"
    assert output["glyph_compatible_games"]==0

print("PASS: Switch 1 base titles remain eligible when Switch 2 upgrade edition exists")
print("PASS: Switch 2-only 0400 identifiers, software updates, and regional duplicate IDs excluded")
print("NOTE: accepted 0100 title IDs are candidates, not audited unique retail games")
