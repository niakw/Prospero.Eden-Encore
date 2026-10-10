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

catalog={"schema":1,"scope":"switch1_base_game_research_candidates_only",
         "game_count":2,"games":[{"title_id":"01007EF00011E000",
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
    audit=json.loads((root/"catalog/scope-audit.json").read_text())
    assert audit["switch1_candidate_title_ids"]==2
    try:
        store.switch1_scope_audit(dict(catalog,scope="switch1_metadata_all_supplied_regions"))
    except ValueError:pass
    else:raise AssertionError("legacy unfiltered Switch1 catalog was accepted")
    assert audit["excludes_switch2_only_0400"]
    assert audit["includes_titles_also_released_for_switch2"]
    assert audit["different_preferred_display_names"]==2
    invalid_catalog=dict(catalog,games=[
        *catalog["games"],
        {"title_id":"0400C3F00006E000","title":"Mario Kart World"}])
    try:
        store.switch1_scope_audit(invalid_catalog)
    except ValueError:pass
    else:raise AssertionError("Switch 2 only title was incorrectly included")
    dual_release=dict(catalog,games=[
        *catalog["games"],
        {"title_id":"0100F43008C44000","title":"Pokemon Legends Z-A"}])
    assert store.switch1_scope_audit(dual_release)["switch1_candidate_title_ids"]==3
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
    raw_run={"schema":1,"run_id":"test-github-shard-0",
             "providers":[{"provider":"github","completed":3,"attempted":4,
                           "blocked_or_failed":1,"source_leads":1}],
             "total_attempts":4,"total_completed":3,
             "total_blocked_or_failed":1,"source_leads_observed":1}
    cumulative={"schema":1,"latest_run_id":raw_run["run_id"],
                "recent_runs":[{"schema":1,"run_id":"older-shard","providers":[],
                                "total_attempts":1,"total_completed":1,
                                "total_blocked_or_failed":0},raw_run]}
    assert store.latest_run_metrics(cumulative)==raw_run
    stats=store.persist(root,current,newstate,catalog,queue,cumulative)
    metrics=json.loads((root/"discovery/metrics.json").read_text())
    assert metrics["latest_run_id"]=="test-github-shard-0"
    assert metrics["latest_run_completed"]==3
    assert metrics["latest_run_blocked"]==1
    assert metrics["completed_distinct_query_keys"]==2
    assert stats["accumulated_mod_leads"]==2
    try:
        store.latest_run_metrics(dict(cumulative,latest_run_id="lost-run"))
    except ValueError:pass
    else:raise AssertionError("missing latest run must be rejected")
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
