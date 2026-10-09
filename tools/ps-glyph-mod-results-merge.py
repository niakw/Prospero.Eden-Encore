#!/usr/bin/env python3
"""Accumulate metadata-only console glyph mod leads across incremental searches.

Deduplicated by Switch title ID and canonical page URL. No downloads,
raw HTML, credentials or game bytes are stored. Always preserve provenance.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

MAX_DOC = 64 * 1024 * 1024
MAX_GAMES = 250000
MAX_LEADS = 500000

def check_file(file: Path):
    if not file.is_file() or file.is_symlink() or file.stat().st_size > MAX_DOC:
        raise ValueError("unsafe source lead report")
    d=json.loads(file.read_text("utf-8"))
    if d.get("schema")!=1:
        raise ValueError("invalid source schema")
    return d

def merge(reports:list[dict]) -> dict:
    by_tid={}
    count=0
    for doc in reports:
        if doc.get("schema")!=1:
            raise ValueError("invalid discovery result")
        # Both batch reports and merged historical reports have games[].
        for row in doc.get("games",[]):
            tid=row.get("title_id")
            if not isinstance(tid,str) or len(tid)!=16:
                raise ValueError("malformed researched Switch game ID")
            obj=by_tid.setdefault(tid,{
                "title_id":tid,"game":row.get("game",""),
                "leads":[],"queries":[],"search_links":{},
                "mod_pack_ready":False,"title_update_romfs_verified":False})
            for lead in row.get("leads",[])[:40]:
                if lead.get("safety")!="UNVERIFIED_SOURCE_LEAD" or not lead.get("url"):
                    continue
                key=(lead["url"].lower(),lead.get("provider",""))
                if any((x["url"].lower(),x.get("provider",""))==key for x in obj["leads"]):
                    continue
                if len(obj["leads"])<100:
                    obj["leads"].append(lead)
                count+=1
                if count>MAX_LEADS:
                    raise ValueError("too many source leads")
            # Historical merged data stores multiple queries[] per game;
            # do not discard their provenance on the next incremental run.
            query_entries=list(row.get("queries",[]))
            if row.get("query"):
                query_entries.append({"q":row["query"],
                                      "status":row.get("discovery_status","unknown")})
            for v in query_entries:
                if (isinstance(v,dict) and
                    isinstance(v.get("q"),str) and
                    isinstance(v.get("status"),str) and
                    v not in obj["queries"] and len(obj["queries"])<80):
                    obj["queries"].append({"q":v["q"][:600],
                                           "status":v["status"][:120]})
            links=row.get("search_links") or {}
            for k,v in links.items():
                if isinstance(k,str) and isinstance(v,str):
                    obj["search_links"][k]=v
    if len(by_tid)>MAX_GAMES:
        raise ValueError("too many Switch titles")
    result=sorted(by_tid.values(),key=lambda x:x["title_id"])
    return {"schema":1,"games":result,"game_count":len(result),
            "source_lead_count":sum(len(x["leads"]) for x in result),
            "gameplay_glyphs_autoenabled":0,"assets_downloaded":0,
            "warning":"Resumable search metadata only; no mod packs or Switch runtime rules activated."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reports",nargs="+",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    try:
        if a.out.exists() or a.out.is_symlink() or not a.out.parent.is_dir():
            raise ValueError("output already exists or parent unsafe")
        out=merge([check_file(path) for path in a.reports])
        a.out.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":"))+"\n")
        print("GLYPH SOURCE LEADS",out["source_lead_count"],"in",
              out["game_count"],"Switch 1 title IDs (unverified)")
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print("REJECTED GLYPH SOURCE LEAD MERGE:",exc,file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
