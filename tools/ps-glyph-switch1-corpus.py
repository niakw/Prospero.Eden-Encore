#!/usr/bin/env python3
"""Strictly Switch 1 game-mod candidate corpus, with explicit exclusion evidence.

Public regional TitleDB mixes base applications, storefront variants,
region-localized aliases, demos, preorders and (possibly) Switch2 metadata.
These records are NOT an official catalog of games confirmed playable on
Switch1. Keep "candidate"/"deferred"/"excluded" separate, do not set
"supported" simply because an ID looks like a base application.

Switch1+Switch2 shared games remain candidates by their Switch1 app ID.
Switch2-only 0400 IDs are never included; no arbitrary 8k game cap.
"""
from __future__ import annotations
import argparse
from collections import Counter
import datetime
import importlib.util
import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent

def load(name:str,file:str):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    if not spec or not spec.loader:raise RuntimeError("missing Switch1 metadata helper")
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

titledb=load("eden_title_db_reader","ps-glyph-switch1-titledb.py")
eligible=load("eden_nx1_game_gate","ps-glyph-switch1-eligibility.py")
MAX_REGION_FILES=24
MAX_GAME_ROWS=250000


def raw_entries(records):
    """Yield all structurally valid metadata records while preserving their
    original platform/release/type fields for Switch1 eligibility analysis."""
    if isinstance(records,dict):
        if isinstance(records.get("titles"),(dict,list)):
            records=records["titles"]
        else:
            records=list(records.items())
    if not isinstance(records,list) or len(records)>MAX_GAME_ROWS:
        raise ValueError("unsupported or oversized regional TitleDB")
    for record in records:
        if isinstance(record,(tuple,list)) and len(record)==2:
            key,val=record
            if isinstance(val,dict):
                identifier=(val.get("id") or val.get("titleId")
                            or val.get("title_id") or key)
                name=(val.get("name") or val.get("title")
                      or val.get("description"))
                details=val
            else:
                identifier,name,details=key,val,{}
        elif isinstance(record,dict):
            identifier=(record.get("id") or record.get("titleId")
                        or record.get("title_id") or record.get("tid"))
            name=(record.get("name") or record.get("title")
                  or record.get("description"))
            details=record
        else:continue
        if not isinstance(identifier,str) or not isinstance(name,str):
            continue
        name=name.strip()
        if not name or len(name)>320 or not titledb.clean_name(name):
            continue
        if not (eligible.SWITCH1_ID.fullmatch(identifier.upper())
                or eligible.SWITCH2_ID.fullmatch(identifier.upper())):
            continue
        yield identifier.upper(),name,eligible.source_metadata(details)


def merge(regions:list[Path],known:list[str]|None=None,
          asof:datetime.date|None=None)->dict:
    if not 1<=len(regions)<=MAX_REGION_FILES:
        raise ValueError("need 1-24 regional databases")
    asof=asof or datetime.date.today()
    aliases={titledb.clean_name(x) for x in (known or [])
             if titledb.clean_name(x)}
    rows={}
    sources=[]
    switch2_exclusives=0
    for region in regions:
        data,digest=titledb.read_json(region,titledb.MAX_DB_BYTES)
        count=0
        switch2_in_region=0
        for tid,label,metadata in raw_entries(data):
            if eligible.SWITCH2_ID.fullmatch(tid):
                switch2_in_region+=1
                continue
            record=rows.setdefault(tid,{"labels":set(),"entries":[]})
            record["labels"].add(label)
            # Keep each regional name attached to ITS OWN platform/type/date.
            # A separate region's full-game listing must not accidentally
            # erase the fact that this particular entry is a demo.
            record["entries"].append((label,metadata))
            count+=1
            if len(rows)>MAX_GAME_ROWS:
                raise ValueError("Switch1 metadata exceeds supported size")
        sources.append({"filename":region.name,"sha256":digest,
                        "switch1_base_rows":count,
                        "switch2_only_id_rows_excluded":switch2_in_region})
        switch2_exclusives+=switch2_in_region
    if not rows:
        raise ValueError("no Switch 1-shaped applications in supplied regions")
    games=[]
    exclusions=Counter()
    exclusions_sample=[]
    deferred=0
    for tid,value in rows.items():
        labels=sorted(value["labels"],key=lambda x:(len(x),x.casefold()))
        # Review each alias with its own metadata, then pick a display name
        # from qualifying FULL-GAME regional records only.
        reviews=[(name,eligible.classify(tid,name,meta,asof))
                 for name,meta in value["entries"]]
        accepted={name for name,verdict in reviews
                  if verdict["decision"]=="candidate"}
        if not accepted:
            classifications=[verdict["reason"] for _,verdict in reviews]
            reason=Counter(classifications).most_common(1)[0][0]
            exclusions[reason]+=1
            if any(verdict["decision"]=="defer" for _,verdict in reviews):
                deferred+=1
            if len(exclusions_sample)<120:
                exclusions_sample.append({"title_id":tid,
                                          "title":labels[0],"reason":reason})
            continue
        full_labels=sorted(accepted,key=lambda x:(len(x),x.casefold()))
        exact=next((x for x in full_labels
                    if titledb.clean_name(x) in aliases),None)
        preferred=exact or full_labels[0]
        games.append({
            "title_id":tid,"title":preferred,"aliases":labels[:12],
            "previously_researched_title":bool(exact),
            "eligibility":"switch1_metadata_candidate_not_verified",
            "switch1_game_officially_verified":False,
            "also_available_on_switch2_allowed":True,
            "title_id_platform_family":"Nintendo Switch 1 (NX1)",
            "game_update_verified":False,"glyph_pack_validated":False})
    games.sort(key=lambda x:(not x["previously_researched_title"],
                             x["title"].casefold(),x["title_id"]))
    return {"schema":1,
            "scope":"switch1_base_game_research_candidates_only",
            "game_count":len(games),
            "officially_verified_switch1_game_count":0,
            "raw_switch1_application_ids":len(rows),
            "switch2_only_id_rows_excluded":switch2_exclusives,
            "non_game_or_pre_release_title_ids_excluded":sum(exclusions.values()),
            "deferred_until_released_count":deferred,
            "exclusion_reason_counts":dict(sorted(exclusions.items())),
            "sample_excluded":exclusions_sample,
            "eligible_on_switch1_and_switch2":True,
            "source_regions":sources,
            "games":games,"glyph_compatible_games":0,
            "warning":("Filtered community metadata only; no claim that the "
                       "remaining rows are all released official Switch1 games. "
                       "Cross-released Switch1/Switch2 titles remain in scope; "
                       "0400 Switch2-only IDs, demos, DLC and unavailable "
                       "listings do not become glyph targets.")}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--regions",nargs="+",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink() or not args.out.parent.is_dir():
            raise ValueError("new output path required")
        original=json.loads((HERE.parent/"docs/PS_GLYPH_SOURCE_INDEX.json").read_text())
        seeds=json.loads((HERE.parent/"docs/PS_GLYPH_SWITCH1_GAME_SEEDS.json").read_text())
        names=([x["title"] for x in original["mods"]]+
               [x["switch_game"] for x in seeds["games"]])
        catalog=merge(args.regions,names)
        args.out.write_text(json.dumps(catalog,ensure_ascii=False,
                                       separators=(",",":"))+"\n")
        print("SWITCH 1 MOD RESEARCH CANDIDATES",catalog["game_count"],
              "from",catalog["raw_switch1_application_ids"],"NX1-shaped IDs;",
              catalog["non_game_or_pre_release_title_ids_excluded"],"excluded;",
              catalog["switch2_only_id_rows_excluded"],"Switch2-only ID rows;"
              " zero games officially qualified")
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as exc:
        print("INVALID SWITCH1 ELIGIBILITY CORPUS:",exc,file=sys.stderr)
        return 1
    return 0

if __name__=="__main__":
    raise SystemExit(main())
