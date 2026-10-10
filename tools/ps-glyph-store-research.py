#!/usr/bin/env python3
"""Merge and persist large Switch glyph research snapshots on a moving Git branch.

Invoked after fetching current dev branch in Actions. Never delete prior
source URLs or previously completed provider+console queries merely because
a newly indexed TitleDB reordered game rows. Refuse raw HTML, secret or
binary mod assets. Catalog/search queue stored as deterministic gzip.
"""
from __future__ import annotations
import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import sys

MAX_JSON=128*1024*1024
MAX_SOURCE_LEADS=500000
HERE=Path(__file__).resolve().parent

sp=importlib.util.spec_from_file_location(
    "eden_store_mod_source_merge",HERE/"ps-glyph-mod-results-merge.py")
assert sp and sp.loader
modmerge=importlib.util.module_from_spec(sp)
sp.loader.exec_module(modmerge)


def read(path:Path|None)->dict:
    if path is None or not path.exists():return {}
    if not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_JSON:
        raise ValueError("invalid metadata source")
    value=json.loads(path.read_text("utf-8"))
    if not isinstance(value,dict) or value.get("schema")!=1:
        raise ValueError("unrecognized metadata schema")
    return value


def state(old:dict,new:dict)->dict:
    if new.get("schema")!=1 or not isinstance(new.get("completed_query_keys"),list):
        raise ValueError("new research search progress is invalid")
    if old and (old.get("schema")!=1 or
                not isinstance(old.get("completed_query_keys",[]),list)):
        raise ValueError("prior durable progress is invalid")
    out=dict(new)
    for key in ("completed_query_keys","completed_title_ids"):
        rows=set(old.get(key,[])) | set(new.get(key,[]))
        if any(not isinstance(x,str) or len(x)>180 for x in rows) or len(rows)>3000000:
            raise ValueError("bad progress identity data")
        out[key]=sorted(rows)
    # The stored offset is an optimization, not our source of correctness.
    # On different catalog ordering/provider/variant, restart sweep and skip
    # durable completed keys. Never mark unseen provider tasks as complete.
    same=(old and old.get("catalog_sha256")==new.get("catalog_sha256") and
          old.get("last_provider")==new.get("last_provider") and
          old.get("search_variant")==new.get("search_variant"))
    if same:
        out["next_offset"]=max(old.get("next_offset",0),new.get("next_offset",0))
    else:
        out["next_offset"]=0
    out["completed_catalog_scan"]=False
    return out


def persist(root:Path, fresh_leads:dict, fresh_progress:dict,
            catalog:dict, queue:dict, run_metrics:dict|None=None)->dict:
    if any(x.get("schema")!=1 for x in (fresh_leads,fresh_progress,catalog,queue)):
        raise ValueError("unrecognized research format")
    if queue.get("total_search_tasks")!=4*queue.get("distinct_game_title_ids",0):
        raise ValueError("wrong 4-platform whole-catalog queries")
    if catalog.get("game_count")!=queue.get("distinct_game_title_ids"):
        raise ValueError("queue and catalog game count disagree")
    research=root/"discovery"
    store=root/"catalog"
    research.mkdir(parents=True,exist_ok=True)
    store.mkdir(parents=True,exist_ok=True)
    previous_leads=read(research/"leads.json")
    previous_progress=read(research/"progress.json")
    merged=modmerge.merge([x for x in (previous_leads,fresh_leads) if x])
    progress=state(previous_progress,fresh_progress)
    data={"leads.json":merged,"progress.json":progress}
    if run_metrics is not None:
        if (run_metrics.get("schema")!=1 or
            not isinstance(run_metrics.get("providers"),list) or
            not isinstance(run_metrics.get("run_id"),str) or
            not all(type(run_metrics.get(k)) is int
                for k in ("total_attempts","total_completed","total_blocked_or_failed"))):
            raise ValueError("invalid live request results")
        previous = read(research/"metrics.json")
        recent = previous.get("recent_runs",[]) if previous else []
        if not isinstance(recent,list) or len(recent)>150:
            raise ValueError("unbounded previous run evidence")
        merged_runs={v["run_id"]:v for v in recent if isinstance(v,dict)
                     and isinstance(v.get("run_id"),str)}
        merged_runs[run_metrics["run_id"]]=run_metrics
        # Ordered insertions: keep up to 50 prior+new authenticated
        # runs so numbers are inspectable after Actions artifacts expire.
        runs=list(merged_runs.values())[-50:]
        data["metrics.json"]={
            "schema":1, "run_count_retained":len(runs),
            "latest_run_id":run_metrics["run_id"],
            "latest_run_completed":run_metrics["total_completed"],
            "latest_run_attempted":run_metrics["total_attempts"],
            "latest_run_blocked":run_metrics["total_blocked_or_failed"],
            "cumulative_retained_completed":sum(v.get("total_completed",0) for v in runs),
            "completed_distinct_query_keys":len(progress["completed_query_keys"]),
            "unique_mod_source_leads":merged["source_lead_count"],
            "recent_runs":runs,
        }
    for file,content in data.items():
        (research/file).write_text(
            json.dumps(content,ensure_ascii=False,separators=(",",":"))+"\n",
            encoding="utf-8")
    for file,doc in (("switch1-titles.json.gz",catalog),
                     ("source-queries.json.gz",queue)):
        encoded=json.dumps(doc,ensure_ascii=False,
                           separators=(",",":")).encode("utf-8")
        with (store/file).open("wb") as output:
            with gzip.GzipFile(filename="",fileobj=output,
                               mode="wb",compresslevel=9,mtime=0) as stream:
                stream.write(encoded)
    return {"known_game_ids":catalog["game_count"],
            "total_research_queries":queue["total_search_tasks"],
            "accumulated_mod_leads":merged["source_lead_count"],
            "completed_provider_queries":len(progress["completed_query_keys"])}


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root",type=Path,required=True)
    p.add_argument("--fresh-leads",type=Path,required=True)
    p.add_argument("--fresh-state",type=Path,required=True)
    p.add_argument("--catalog",type=Path,required=True)
    p.add_argument("--search-queue",type=Path,required=True)
    p.add_argument("--run-metrics",type=Path)
    a=p.parse_args()
    try:
        if not a.out_root.is_dir() or a.out_root.is_symlink():
            raise ValueError("unsafe metadata repository root")
        stats=persist(a.out_root,read(a.fresh_leads),read(a.fresh_state),
                      read(a.catalog),read(a.search_queue),
                      read(a.run_metrics) if a.run_metrics else None)
        print("GITHUB RESEARCH CHECKPOINT:",stats)
        return 0
    except (OSError,ValueError,TypeError,KeyError) as error:
        print("REJECTED GITHUB RESEARCH STORE:",error,file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
