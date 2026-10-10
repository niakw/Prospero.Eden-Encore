#!/usr/bin/env python3
"""Synthetic Switch1 published/shared-vs-Switch2-only title qualification."""
from __future__ import annotations
import datetime
import importlib.util
import json
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
def loader(name,file):
    s=importlib.util.spec_from_file_location(name,HERE/file)
    assert s and s.loader
    x=importlib.util.module_from_spec(s)
    s.loader.exec_module(x)
    return x

gate=loader("eden_switch1_only_title_gate","ps-glyph-switch1-eligibility.py")
corpus=loader("eden_switch1_only_corpus","ps-glyph-switch1-corpus.py")
today=datetime.date(2026,10,10)
nx1="01007EF00011E000"
nx2="040057C02159A000"
same="0100000000010000"
demo="0100777011222000"
cloud="0100666011222000"
future="0100555011222000"
dlc="0100444011222000"
shared=gate.classify(nx1,"The Legend of Zelda: Breath of the Wild",
                     {"platforms":["Nintendo Switch","Nintendo Switch 2"],
                      "type":"Game","releaseDate":"2017-03-03"},today)
assert shared["decision"]=="candidate" and shared["switch2_edition_also_possible"]
assert not shared["switch1_confirmed"]
assert gate.classify(nx2,"Mario Kart World",{},today)["reason"]=="switch2_only_application_id"
assert gate.classify(nx1,"No Native Switch1 Edition",
                     {"platforms":["Nintendo Switch 2"],"type":"Game"},
                     today)["decision"]=="exclude"
assert gate.classify(demo,"Game (Demo Version)",{},today)["reason"]=="named_demo_or_trial"
assert gate.classify(cloud,"Cloudy Game - Cloud Version",{},today)["reason"]=="streaming_only_cloud_edition"
assert gate.classify(dlc,"Game DLC",{"type":"DLC"},today)["decision"]=="exclude"
assert gate.classify(future,"Coming Soon",
                     {"releaseDate":"2027-01-30"},today)["decision"]=="defer"
assert gate.classify(same,"Mario Odyssey",
                     {"releaseDate":"2017-10-27"},today)["decision"]=="candidate"
assert gate.classify(nx1,"Title",{"type":"GAME","platform":"Switch2, Switch"},today)["decision"]=="candidate"
assert gate.classify(nx1,"Title",{"type":"non-game application"},today)["decision"]=="exclude"

with tempfile.TemporaryDirectory(prefix="eden-switch1-strict-corpus-") as directory:
    base=Path(directory)
    us={
        "100":{"id":nx1,"name":"The Legend of Zelda: Breath of the Wild",
               "platforms":["Nintendo Switch","Nintendo Switch 2"],"releaseDate":"2017-03-03"},
        "101":{"id":nx2,"name":"Mario Kart World"},
        "102":{"id":demo,"name":"Big Adventure Demo"},
        "103":{"id":cloud,"name":"Cloudy Game - Cloud Version"},
        "104":{"id":future,"name":"Another Game",
               "releaseDate":"2027-04-01"},
        "105":{"id":dlc,"name":"Zelda DLC","type":"DLC"},
        "106":{"id":same,"name":"Super Mario Odyssey"},
    }
    fr={
        "200":{"id":nx1,"name":"Zelda: Breath of the Wild"},
        "201":{"id":same,"name":"Super Mario Odyssey","releaseDate":"2017-10-27"},
    }
    pa,pb=base/"US.en.json",base/"FR.fr.json"
    pa.write_text(json.dumps(us))
    pb.write_text(json.dumps(fr))
    result=corpus.merge([pa,pb],["Zelda: Breath of the Wild"],today)
    assert result["scope"]=="switch1_base_game_research_candidates_only"
    assert result["game_count"]==2,result
    assert result["raw_switch1_application_ids"]==6
    assert result["switch2_only_id_rows_excluded"]==1
    assert result["non_game_or_pre_release_title_ids_excluded"]==4
    assert result["deferred_until_released_count"]==1
    assert result["officially_verified_switch1_game_count"]==0
    assert result["games"][0]["title_id"]==nx1
    assert result["games"][0]["previously_researched_title"]
    assert "Zelda" in result["games"][0]["title"]
    assert {x["title_id"] for x in result["games"]}=={nx1,same}
    assert all(not x["switch1_game_officially_verified"] for x in result["games"])
print("PASS: Switch2-only IDs, DLC, demos, cloud apps, unreleased titles are not Switch1 mod work")
print("PASS: BOTW and other games shared with Switch2 RETAIN original Switch1 game identity")
print("PASS: no arbitrary 4k/8k cap or mistaken claim of 24k officially verified games")
