#!/usr/bin/env python3
"""Synthetic durable research merge under concurrent dev branch changes."""
from __future__ import annotations
import gzip
import importlib.util
import json
import tempfile
from pathlib import Path

sp=importlib.util.spec_from_file_location(
    "eden_glyph_research_store",Path(__file__).with_name("ps-glyph-store-research.py"))
assert sp and sp.loader
store=importlib.util.module_from_spec(sp)
sp.loader.exec_module(store)

catalog={"schema":1,"game_count":2,"games":[{"title_id":"01007EF00011E000",
     "title":"Zelda Breath of the Wild"},{"title_id":"0100AAA000111000",
     "title":"Persona 3 Portable"}]}
queue={"schema":1,"distinct_game_title_ids":2,"total_search_tasks":8,"games":[]}
def link(url,provider):
    return {"url":url,"provider":provider,"safety":"UNVERIFIED_SOURCE_LEAD"}
remote={"schema":1,"games":[{"title_id":"01007EF00011E000","game":"BOTW",
        "leads":[link("https://gamebanana.com/mods/659253","duckduckgo")]}]}
current={"schema":1,"games":[{"title_id":"01007EF00011E000","game":"BOTW",
        "leads":[link("https://gamebanana.com/mods/659253","duckduckgo"),
                 link("https://github.com/test/wiiu-ps4-buttons","github")]}]}
oldstate={"schema":1,"catalog_sha256":"A","last_provider":"github",
          "search_variant":0,"next_offset":3,
          "completed_query_keys":["github|0|01007EF00011E000"],
          "completed_title_ids":["01007EF00011E000"]}
newstate={"schema":1,"catalog_sha256":"A","last_provider":"github",
          "search_variant":0,"next_offset":5,
          "completed_query_keys":["github|0|0100AAA000111000"],
          "completed_title_ids":["0100AAA000111000"]}
with tempfile.TemporaryDirectory(prefix="eden-mod-research-store-") as t:
    home=Path(t)
    root=home/"glyph-research"
    root.mkdir()
    (root/"discovery").mkdir()
    (root/"discovery"/"leads.json").write_text(json.dumps(remote))
    (root/"discovery"/"progress.json").write_text(json.dumps(oldstate))
    stats=store.persist(root,current,newstate,catalog,queue)
    assert stats["accumulated_mod_leads"]==2
    assert stats["total_research_queries"]==8
    assert stats["completed_provider_queries"]==2
    persisted=json.loads((root/"discovery"/"progress.json").read_text())
    assert persisted["next_offset"]==5
    assert len(persisted["completed_query_keys"])==2
    for f in ("switch1-titles.json.gz","source-queries.json.gz"):
        with gzip.open(root/"catalog"/f,"rt") as stream:
            assert json.load(stream)["schema"]==1
    first=(root/"catalog"/"source-queries.json.gz").read_bytes()
    store.persist(root,current,newstate,catalog,queue)
    assert (root/"catalog"/"source-queries.json.gz").read_bytes()==first
    another=dict(newstate,last_provider="firefox_yandex")
    store.persist(root,current,another,catalog,queue)
    assert json.loads((root/"discovery"/"progress.json").read_text())["next_offset"]==0
    assert len(json.loads((root/"discovery"/"leads.json").read_text())["games"][0]["leads"])==2
    try:
        store.persist(root,current,newstate,catalog,
                      dict(queue,total_search_tasks=7))
    except ValueError:pass
    else:raise AssertionError("accepted incomplete search queue")
print("PASS: concurrent result union, provider scope and deterministic gzip catalog persistence")
print("PASS: no prior game mods lost; invalid catalog/queue rejected")
