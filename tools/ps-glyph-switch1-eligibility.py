#!/usr/bin/env python3
"""Filter Switch1 mod research targets using versioned storefront metadata.

A 0100...000 application-shaped Nintendo NX ID is a *Switch 1 candidate*,
NOT necessarily a released game. Exclude demonstrably Switch 2-only 0400
titles, updates/DLC, demos and non-game apps when metadata proves the type.
Preserve Switch1 editions of games ALSO released on Switch2: the existence
of a Switch2 edition is NOT grounds to exclude the Switch1 version.

No arbitrary "4k-8k" cap: public catalog counts vary and an unverified
TitleDB row is never reported as an officially verified playable game.
"""
from __future__ import annotations

import datetime
import re
from typing import Any

SWITCH1_ID=re.compile(r"0100[0-9A-Fa-f]{9}000\Z")
SWITCH2_ID=re.compile(r"0400[0-9A-Fa-f]{9}000\Z")
DEMO_PATTERN=re.compile(
    r"(?:^|[\s\[(\-–])(?:demo|demonstration|trial version|free trial|"
    r"version d'essai|démo)(?:$|[\s\])\-–:])",re.I)
CLOUD_PATTERN=re.compile(r"(?:\bcloud version\b|\bcloud edition\b|クラウドバージョン)",re.I)
GAME_TYPE={"game","games","base game","application","full game"}
NON_GAME_TYPES={"dlc","downloadable content","add-on","addon","update",
                "patch","system application","theme","soundtrack","trailer",
                "video","demo","trial","non-game application","tool"}
DATE_FIELDS=("releaseDate","release_date","firstReleaseDate",
             "releaseDateUTC","release_date_iso")
METADATA_PLATFORMS=("platforms","platform","platformName","console","hardware")
TYPE_FIELDS=("type","productType","contentType","kind","applicationType")

def _flatten(x:Any)->list[str]:
    if isinstance(x,str):return [x]
    if isinstance(x,list):return sum((_flatten(v) for v in x[:30]),[])
    if isinstance(x,dict):
        return sum((_flatten(v) for k,v in x.items() if k in
                    ("name","platform","platformName","system","code")),[])
    return []

def _platforms(raw:dict)->tuple[bool,bool,bool]:
    """Return (has_explicit_platform_metadata, NX1, NX2)."""
    records=[]
    for key in METADATA_PLATFORMS:
        if key in raw:records.extend(_flatten(raw[key]))
    if not records:return False,False,False
    one=two=False
    for label in records:
        normalized=re.sub(r"[\s\-]+"," ",label.casefold()).strip()
        if (re.search(r"\b(nintendo )?switch 2\b|\bns2\b",normalized)
            or "switch2" in normalized):
            two=True
        elif (re.search(r"\b(nintendo )?switch\b|\bnsw\b",normalized)
              or normalized in ("nx","hac")):
            one=True
    return True,one,two

def _type_value(raw:dict)->str|None:
    values=[]
    for key in TYPE_FIELDS:
        if key in raw:values.extend(_flatten(raw[key]))
    return next((v.strip().casefold() for v in values if v.strip()),None)

def _release(raw:dict)->datetime.date|None:
    for field in DATE_FIELDS:
        v=raw.get(field)
        if not isinstance(v,(str,int)):continue
        digits=re.sub("[^0-9]","",str(v))
        if len(digits)<8:continue
        try:
            date=datetime.date(int(digits[:4]),int(digits[4:6]),int(digits[6:8]))
        except ValueError:continue
        if 2016<=date.year<=2100:return date
    return None

def classify(tid:str,name:str,metadata:dict|None=None,
             asof:datetime.date|None=None)->dict:
    metadata=metadata or {}
    asof=asof or datetime.date.today()
    upper=tid.upper() if isinstance(tid,str) else ""
    candidates=[]
    if SWITCH2_ID.fullmatch(upper):
        return {"decision":"exclude","reason":"switch2_only_application_id",
                "switch1_confirmed":False}
    if not SWITCH1_ID.fullmatch(upper):
        return {"decision":"exclude","reason":"not_switch1_base_application_id",
                "switch1_confirmed":False}
    explicit,has_one,has_two=_platforms(metadata)
    if explicit and has_two and not has_one:
        return {"decision":"exclude","reason":"explicit_switch2_only_platform_metadata",
                "switch1_confirmed":False}
    if explicit and not has_one and not has_two:
        candidates.append("platform_field_does_not_identify_switch1")
    t=_type_value(metadata)
    if t in NON_GAME_TYPES:
        return {"decision":"exclude","reason":"content_type_"+re.sub(r"\W+","_",t),
                "switch1_confirmed":False}
    if t and t not in GAME_TYPE:
        candidates.append("unrecognized_product_type")
    if DEMO_PATTERN.search(name):
        return {"decision":"exclude","reason":"named_demo_or_trial",
                "switch1_confirmed":False}
    if CLOUD_PATTERN.search(name):
        return {"decision":"exclude","reason":"streaming_only_cloud_edition",
                "switch1_confirmed":False}
    date=_release(metadata)
    if date and date>asof:
        return {"decision":"defer","reason":"not_released_on_scan_date",
                "available_from":date.isoformat(),"switch1_confirmed":False}
    # A game's Switch 2 edition can coexist with its actual NX1 release;
    # only an explicit Switch2-only field (above) excludes the NX1 candidate.
    # A TitleDB record alone cannot affirm official game status.
    return {"decision":"candidate",
            "reason":"switch1_base_id_and_no_known_exclusion",
            "switch1_confirmed":False,
            "switch2_edition_also_possible":bool(has_two),
            "verification_needed":candidates or [
                "independent_switch1_game_or_official_store_verification"]}

def source_metadata(record:dict)->dict:
    """Do not materialize unsupported fields; keep only classification inputs."""
    keys=METADATA_PLATFORMS+TYPE_FIELDS+DATE_FIELDS
    return {key:record[key] for key in keys if key in record}
