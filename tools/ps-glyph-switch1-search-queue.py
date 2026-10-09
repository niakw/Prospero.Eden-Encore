#!/usr/bin/env python3
"""Materialize all Switch 1 title-specific PC/console/controller-mod search paths.

Produces a complete zero-request research queue even when search engines
rate-limit the incremental workers. Four variants per TitleID: Switch,
multiplatform PC/WiiU/PS/Xbox, GameBanana, Russian/other-region. This is
NOT a claim that the public Internet has four useful results per game.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location(
    "eden_full_console_mod_queries",ROOT/"ps-glyph-mod-discovery.py")
if spec is None or spec.loader is None:
    raise SystemExit("missing query engine")
discovery=importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)

def queue(catalog:dict)->dict:
    if catalog.get("schema")!=1 or not isinstance(catalog.get("games"),list):
        raise ValueError("invalid Switch game title metadata")
    games=catalog["games"]
    if not 1<=len(games)<=discovery.MAX_CATALOG:
        raise ValueError("out-of-range complete Switch1 discovery catalog")
    items=[]
    for title in games:
        queries=[]
        for var in range(4):
            query=discovery.game_query(title["title"],var)
            queries.append({"variant":var,
                            "platform_scope":["Switch","PC/WiiU/PS/Xbox",
                                               "GameBanana direct","Russian other-region"][var],
                            "query":query,"providers":discovery.search_urls(query),
                            "searched":False,"source_mod_identified":False})
        items.append({"title_id":title["title_id"],"name":title["title"],
                      "queries":queries,"game_compatible":False})
    return {"schema":1,"scope":"ALL_PUBLIC_CATALOGUED_SWITCH_1_TITLES",
            "distinct_game_title_ids":len(items),
            "total_search_tasks":len(items)*4,
            "games":items,"mod_downloads":0,
            "note":"Search URL work queue only; incremental workers enforce provider rate limits. No Switch glyph compatibility claimed."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink() or not args.out.parent.is_dir():
            raise ValueError("queue destination must be new")
        data=discovery.read_json(args.catalog,128*1024*1024)
        out=queue(data)
        args.out.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":"))+"\n")
        print("ALL SWITCH 1 GLYPH SOURCE QUERIES:",out["total_search_tasks"],
              "across",out["distinct_game_title_ids"],"distinct base games")
        return 0
    except (ValueError,OSError,TypeError,KeyError) as error:
        print("SEARCH QUEUE BLOCKED",error,file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
