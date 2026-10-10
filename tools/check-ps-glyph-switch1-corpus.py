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
    assert output["scope"]=="switch1_base_game_research_candidates_only"
    assert output["officially_verified_switch1_game_count"]==0
    assert output["glyph_compatible_games"]==0

with tempfile.TemporaryDirectory(prefix="eden-switch1-regional-alias-") as temp:
    a,b=Path(temp)/"first.json",Path(temp)/"second.json"
    tid="0100ABC000111000"
    demo_only="0100DEF000111000"
    a.write_text(json.dumps({
        "demo": {"id":tid,"name":"Island Explorer: Demo!",
                 "platform":"Nintendo Switch"},
        "only": {"id":demo_only,"name":"Island Playtest",
                 "platform":"Nintendo Switch"}
    }))
    b.write_text(json.dumps({
        "retail": {"id":tid,"name":"Island Explorer",
                   "platform":"Nintendo Switch",
                   "type":"Game","releaseDate":"2024-01-01"}
    }))
    qualified=tool.merge([a,b])
    assert qualified["game_count"]==1,qualified
    assert qualified["games"][0]["title_id"]==tid
    assert qualified["games"][0]["title"]=="Island Explorer"
    assert qualified["non_game_or_pre_release_title_ids_excluded"]==1

print("PASS: Switch 1 base titles remain eligible when Switch 2 upgrade edition exists")
print("PASS: Switch 2-only 0400 identifiers, software updates, and regional duplicate IDs excluded")
print("NOTE: accepted 0100 title IDs are candidates, not audited unique retail games")
