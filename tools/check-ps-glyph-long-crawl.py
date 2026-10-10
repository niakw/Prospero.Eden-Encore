#!/usr/bin/env python3
"""Synthetic no-network long sweep, recovery, and provider-throttle tests."""
from __future__ import annotations
import gzip
import importlib.util
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

tool=Path(__file__).with_name("ps-glyph-long-crawl.py")
spec=importlib.util.spec_from_file_location("eden_crawl_runner_tests",tool)
assert spec and spec.loader
run=importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

catalog={"schema":1,"game_count":2,"games":[
    {"title_id":"01007EF00011E000","title":"Zelda Breath of the Wild"},
    {"title_id":"0100AAA000111000","title":"Persona 3 Portable"}]}
queue={"schema":1,"distinct_game_title_ids":2,"total_search_tasks":8,"games":[]}

with tempfile.TemporaryDirectory(prefix="eden-long-crawl-test-") as root:
    home=Path(root)
    data=home/"data/glyph-research"
    (data/"catalog").mkdir(parents=True)
    (data/"discovery").mkdir()
    for name,doc in (("switch1-titles.json.gz",catalog),("source-queries.json.gz",queue)):
        with gzip.open(data/"catalog"/name,"wt",encoding="utf-8") as handle:
            json.dump(doc,handle)
    requests=[]
    def fake_github(query):
        requests.append(query)
        return [("Zelda Breath of the Wild PS4 gamepad controller glyph mod",
                 "https://github.com/test/zelda-gamepad")] if "Zelda" in query else []
    with patch.object(run.discovery,"github",side_effect=fake_github):
        first,status=run.execute(home,batch_size=1,interval=3.0,retries=0,
                                 run_id="test-job-1",pause=lambda _:None)
        assert status==0 and first["completed"]==2 and first["remaining"]==2
        second,status=run.execute(home,batch_size=1,interval=3.0,retries=0,
                                  run_id="test-job-2",pause=lambda _:None)
        assert status==0 and second["completed"]==2 and second["complete"]
        last,status=run.execute(home,batch_size=1,interval=3.0,retries=0,
                                run_id="test-job-3",pause=lambda _:None)
        assert status==0 and last["complete"] and not last["attempted"]
    assert len(requests)==4
    completed=run.collector.read(data/"discovery/progress.json")[
        "completed_query_keys"]
    assert len(completed)==4
    metrics=run.collector.read(data/"discovery/metrics.json")
    assert metrics["cumulative_retained_completed"]==4
    assert metrics["latest_run_id"]=="test-job-2"
    leads=run.collector.read(data/"discovery/leads.json")
    assert leads["game_count"]==2
    assert not any(g["mod_pack_ready"] for g in leads["games"])
    # Blocked provider: preserve prior successful tasks, do not advance the
    # unprocessed title, and terminate rather than looping forever.
    previous=run.collector.read(data/"discovery/progress.json")
    previous["completed_query_keys"]=previous["completed_query_keys"][:-1]
    (data/"discovery/progress.json").write_text(json.dumps(previous))
    with patch.object(run.discovery,"github",
                      side_effect=run.discovery.ProviderPaused("HTTP 429")):
        blocked,status=run.execute(home,batch_size=1,interval=3.0,retries=0,
                                   run_id="test-blocked",pause=lambda _:None)
    assert status==2 and blocked["failed"]==1
    assert blocked["completed"]==0
    assert not blocked["complete"]
    assert len(run.collector.read(data/"discovery/progress.json")[
        "completed_query_keys"])==3

print("PASS: serial long crawl resumes from stored Title ID and provider/variant keys")
print("PASS: two Switch/PC batches cover all games; blocked provider fails without losing evidence")
