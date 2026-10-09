#!/usr/bin/env python3
"""Build source-backed PC/PS4/Xbox/WiiU/PSP -> Switch 1 glyph port workplans.

Same GAME and same SCENE are reusable across console editions; textures,
compression and file paths are not interchangeable. Adapt spatial placement
and guest-action semantics independently. If authorized original/source
assets are present, existing pixel/layout and ROMFS converters can operate.
Do not copy mod binary bytes or invent missing Switch update fingerprints.

Works against the entire deduplicated multi-region Switch TitleDB corpus.
Joins curated cross-console examples and user-supplied search-result batches,
so new games discovered via DDG, GitHub, Yandex etc enter automatically.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "docs"
MAX_CATALOG = 250000
MAX_LINKS = 250000
ALIASES = {
    "the legend of zelda breath of the wild": "zelda breath of the wild",
    "the legend of zelda tears of the kingdom": "zelda tears of the kingdom",
}
METHODS = {
    "nintendo_yaz0_sarc_bntx_astc": {
        "source_hints": ("sarc", "bntx", "sblarc", "ssarc", "blarc", "astc"),
        "switch_tools": ["ps-glyph-mod-zip-positions.py",
                         "ps-glyph-botw-mod-texture-positions.py",
                         "ps-glyph-bntx-astc.py",
                         "ps-glyph-botw-auto-pack.py"],
        "status": "supported_host_pipeline_only"},
    "nintendo_bfres_layout": {
        "source_hints": ("bfres", "bflyt", "bflan", "bftex", "sarc.zs", "font"),
        "switch_tools": ["ps-glyph-mod-inventory.py", "ps-glyph-platform-coverage.py"],
        "status": "decode_or_repack_adapter_required"},
    "unity_assets": {
        "source_hints": ("unity", "assetbundle", "resources.assets", ".unity3d", "assets"),
        "switch_tools": ["ps-glyph-scene-positions.py", "ps-glyph-cross-platform-image.py"],
        "status": "title_specific_unity_export_repack_required"},
    "unreal_packages": {
        "source_hints": ("unreal", ".pak", ".uasset", "utoc", "ucas"),
        "switch_tools": ["ps-glyph-scene-positions.py", "ps-glyph-cross-platform-image.py"],
        "status": "title_specific_ue_export_repack_required"},
    "atlus_cpk_spr": {
        "source_hints": ("cpk", "spr", "atlus", "persona", "bin"),
        "switch_tools": ["ps-glyph-scene-positions.py", "ps-glyph-cross-platform-image.py"],
        "status": "title_specific_cpk_spr_export_repack_required"},
    "klei_atlas_lua": {
        "source_hints": ("klei", "tex", "lua", "xml atlas", "dont starve"),
        "switch_tools": ["ps-glyph-scene-positions.py", "ps-glyph-cross-platform-image.py"],
        "status": "klei_atlas_compatibility_requires_switch_inspection"},
    "engine_unknown": {
        "source_hints": (),
        "switch_tools": ["ps-glyph-mod-inventory.py", "ps-glyph-cross-platform-image.py",
                         "ps-glyph-scene-positions.py"],
        "status": "identify_runtime_engine_and_binary_formats"},
}

def key(name: str) -> str:
    if not isinstance(name,str):
        return ""
    s=re.sub(r"\s*\((switch|pc|wii u|ps4|ps5|xbox|psp)\)\s*$", "", name, flags=re.I)
    s=re.sub(r"[^\w]+", " ", s.casefold()).strip()
    return ALIASES.get(s,s)

def choose_format(*hints) -> tuple[str,dict]:
    text=" ".join(str(value).casefold() for value in hints)
    ranks={}
    for mode,entry in METHODS.items():
        if mode=="engine_unknown":continue
        ranks[mode]=sum(len(hint) for hint in entry["source_hints"] if hint in text)
    best=sorted(ranks.items(),key=lambda x:(-x[1],x[0]))
    if best and best[0][1]:
        mode=best[0][0]
    else:
        mode="engine_unknown"
    return mode,METHODS[mode]

def mode_for_reference(source: dict) -> str:
    platform=str(source.get("platform","")).lower()
    if "wii u" in platform:return "Wii U"
    if "psp" in platform:return "PSP"
    if "xbox" in platform:return "Xbox"
    if "playstation" in platform or "ps4" in platform or "ps5" in platform:return "PlayStation"
    if "pc" in platform or "steam" in platform:return "PC"
    return "unknown_platform"

def load(path:Path,cap:int=32*1024*1024):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>cap:
        raise ValueError("unsafe metadata input")
    return json.loads(path.read_text("utf-8"))

def plan(catalog:dict,cross:dict,switch:dict,discovery:list[dict]|None=None) -> dict:
    if (catalog.get("schema")!=1 or cross.get("schema")!=1 or
        switch.get("schema")!=1 or
        not isinstance(catalog.get("games"),list) or
        len(catalog["games"])>MAX_CATALOG):
        raise ValueError("invalid game catalogs")
    discovered=discovery or []
    if len(discovered)>MAX_LINKS:
        raise ValueError("unbounded discovered result count")
    matches={}
    for item in cross.get("sources",[]):
        if not isinstance(item,dict) or not key(item.get("switch_game","")):
            raise ValueError("invalid cross-console source")
        matches.setdefault(key(item["switch_game"]),[]).append(item)
    switch_sources={}
    for item in switch.get("mods",[]):
        switch_sources.setdefault(key(item["title"]),[]).append(item)
    by_id={}
    for report in discovered:
        if not isinstance(report,dict) or report.get("schema")!=1:
            raise ValueError("invalid search results")
        for game in report.get("games",[]):
            tid=game.get("title_id")
            if not isinstance(tid,str) or not re.fullmatch("0100[0-9A-Fa-f]{9}000",tid):
                raise ValueError("unsafe discovered title identity")
            for lead in game.get("leads",[])[:20]:
                if lead.get("safety")=="UNVERIFIED_SOURCE_LEAD":
                    by_id.setdefault(tid.upper(),[]).append(lead)
    output=[]
    seen=set()
    for game in catalog["games"]:
        tid=game["title_id"].upper()
        if tid in seen:raise ValueError("duplicate Switch game Title ID")
        seen.add(tid)
        names=game.get("aliases") or [game["title"]]
        direct=[]
        switch_direct=[]
        for label in names:
            direct.extend(matches.get(key(label),[]))
            switch_direct.extend(switch_sources.get(key(label),[]))
        direct=list({s["id"]:s for s in direct}.values())
        switch_direct=list({s["id"]:s for s in switch_direct}.values())
        external=by_id.get(tid,[])
        if not direct and not switch_direct and not external:
            # Whole-catalog mode can be huge; keep a discovery stage without
            # per-game synthetic claims or falsely exported 100k empty plans.
            output.append({"title_id":tid,"switch_title":game["title"],
                           "needs_discovery":True,"references":[],"ready_to_patch":False})
            continue
        references=[]
        for ref in direct:
            mode,adapter=choose_format(ref.get("engine_family",""),
                                       *(ref.get("asset_container_family") or []),
                                       ref.get("asset_path",""))
            references.append({
                "source_id":ref["id"],"source_url":ref["source_url"],
                "source_platform":mode_for_reference(ref),
                "engine":ref.get("engine_family"),
                "source_asset_format":ref.get("asset_container_family",[]),
                "switch_route":mode,"switch_adapter_state":adapter["status"],
                "conversion_tools":adapter["switch_tools"],
                "same_game_scene_lead":ref.get("features",[]),
                "cross_console_positions_reusable":True,
                "source_binary_directly_switch_compatible":False,
                "input_guest_action_a": "ps_cross_if_fixed_eden_ps_profile",
                "controller_right_spatial_icon": "ps_circle",
                "verified_switch_update_hash":None,
                "verified_original_switch_sprite_xywh":None,
                "ready_to_patch":False,
            })
        for ref in switch_direct:
            references.append({
                "source_id":ref["id"],"source_url":ref["source_url"],
                "source_platform":"Switch",
                "switch_adapter_state":"same_platform_mod_original_texture_diff",
                "conversion_tools":["ps-glyph-mod-zip-positions.py",
                                    "ps-glyph-mod-auto-plan.py"],
                "verified_switch_update_hash":None,
                "verified_original_switch_sprite_xywh":ref.get("rect_xywh"),
                "ready_to_patch":False,
            })
        for lead in external[:20]:
            mode,adapter=choose_format(lead.get("page_title",""),
                                       lead.get("url",""))
            references.append({
                "source_id":"search_lead_sha256_"+hashlib.sha256(
                    lead["url"].encode("utf-8")).hexdigest()[:18],
                "source_url":lead["url"],"source_platform":"unknown_or_multiplatform",
                "switch_route":mode,"switch_adapter_state":adapter["status"],
                "conversion_tools":adapter["switch_tools"],
                "original_source_search_engine":lead["provider"],
                "verified_switch_update_hash":None,
                "verified_original_switch_sprite_xywh":None,
                "ready_to_patch":False,
            })
        output.append({"title_id":tid,"switch_title":game["title"],
                       "needs_discovery":False,
                       "source_count":len(references),
                       "has_same_game_other_platform_mod":bool(direct),
                       "has_native_switch_mod":bool(switch_direct),
                       "references":references,"ready_to_patch":False,
                       "next_stage":("Match actual original Nintendo Switch ROMFS, "
                                     "compare relevant original/modded textures; "
                                     "recreate Sony glyphs independently. "
                                     "Use source scene positions as priors.")})
    covered=[r for r in output if not r["needs_discovery"]]
    return {"schema":1,"switch1_title_count":len(output),
            "games_with_research_mod_sources":len(covered),
            "games_without_source_yet":len(output)-len(covered),
            "cross_platform_source_references":sum(
                bool(r.get("has_same_game_other_platform_mod")) for r in covered),
            "game_mod_candidates":output,
            "auto_activated_glyph_packs":0,
            "warning":("Same-game console positions and button semantics are reusable; "
                       "source game's binary texture byte offsets are NOT. "
                       "No archive decoding without matching Nintendo Switch "
                       "original assets and legal source mod access.")}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog",required=True,type=Path)
    p.add_argument("--cross-index",type=Path,
                   default=DOCS/"PS_GLYPH_CROSS_PLATFORM_INDEX.json")
    p.add_argument("--switch-index",type=Path,
                   default=DOCS/"PS_GLYPH_SOURCE_INDEX.json")
    p.add_argument("--discovery-reports",nargs="*",type=Path,default=[])
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink() or not args.out.parent.is_dir():
            raise ValueError("output must be a new file")
        reports=[load(path) for path in args.discovery_reports]
        out=plan(load(args.catalog,128*1024*1024),load(args.cross_index),
                 load(args.switch_index),reports)
        args.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
        print("SWITCH MULTIPLATFORM ADAPTATION",
              out["games_with_research_mod_sources"],"/",out["switch1_title_count"],
              "source-backed game names;",
              out["cross_platform_source_references"],"with cross-console leads;",
              "no runtime packs autoactivated")
        return 0
    except (OSError,ValueError,TypeError,KeyError) as error:
        print("CROSS-PLATFORM ADAPTATION BLOCKED:",error,file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
