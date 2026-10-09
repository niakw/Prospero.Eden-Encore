#!/usr/bin/env python3
"""Adapt real PC/PS4/WiiU modded UI artwork positions into Switch texture candidates.

Inputs: original source-platform RGBA PNG/TGA, same-game source mod artwork,
independently exported original Switch image (may be rescaled/repainted).
Reuses actual changed glyph coordinates (no equal-art requirement) and
original Switch alpha-isolated sprite geometry; never copies copyrighted mod
art into the output or invents image pixel coordinates.

Produces an UNAPPROVED per-game atlas draft. Label proposals may be made
by explicit source filename (e.g. action_A) only for single-sprite files,
but must be verified against the selected static PS5 guest control mapping.
The generated draft intentionally cannot be installed without verification.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
def helper(name,file):
    sp=importlib.util.spec_from_file_location(name,HERE/file)
    if not sp or not sp.loader:raise ValueError("missing image bridge")
    obj=importlib.util.module_from_spec(sp)
    sp.loader.exec_module(obj)
    return obj
cross=helper("eden_same_game_cross_source","ps-glyph-cross-platform-image.py")
semantic=helper("eden_source_semantic_hints","ps-glyph-mod-auto-plan.py")

def draft(source:Path, mod:Path, switch:Path, title_id:str, update:str,
          source_platform:str, scene:str, switch_romfs_path:str):
    import re
    if (not isinstance(title_id,str) or
        not re.fullmatch(r"[0-9a-fA-F]{16}",title_id) or
        not isinstance(update,str) or not update or len(update)>64):
        raise ValueError("invalid matching Switch edition/version")
    report=cross.propose(source,mod,switch,source.stem,source_platform,scene)
    candidates=report["source_ui_layout_position_candidates"]
    if report["original_texture_comparison"]=="rendered_pixels_identical":
        # Exact source/layout match still needs isolated Switch glyph region;
        # never write merely because change components share pixel offsets.
        candidate_exact=report["switch_candidate_rects_xywh"] or []
    else:
        candidate_exact=[]
    # Scene placement priors come from independently decoded Switch original
    # alpha-isolated sprite geometry; safe even when PS4 source differs.
    slots=[]
    count=len(candidates)
    role=semantic.semantic_hint(mod.stem,count)
    for found in candidates:
        slots.append({"rect":found["switch_alpha_sprite_candidate_xywh"],
                      "kind":role["kind"] if role else None,
                      "guest_button":role["guest_button"] if role else None,
                      "source_normalized_center":found["source_normalized_center_xy"],
                      "switch_normalized_center":found["switch_normalized_center_xy"],
                      "reviewed":False})
    return {"schema":1,"title_id":title_id.upper(),"update_version":update,
            "source_platform":source_platform,"scene":scene,
            "switch_romfs_path":switch_romfs_path,
            "source_original_sha256":report["source_original_image_sha256"],
            "source_mod_sha256":report["source_mod_image_sha256"],
            "original_switch_sha256":report["switch_original_image_sha256"],
            "relative_positions_recovered":count,
            "slots":slots,"exact_same_art_component_positions":candidate_exact,
            "same_game_positions_without_equal_art_supported":True,
            "source_mod_art_redistributed":False,
            "ready_to_install":False,
            "next_step":"Review guest action vs physical controller position, then render independent PlayStation icons into exact original Switch resource and verify game update."}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-original",type=Path,required=True)
    parser.add_argument("--source-modded",type=Path,required=True)
    parser.add_argument("--switch-original",type=Path,required=True)
    parser.add_argument("--title-id",required=True)
    parser.add_argument("--update-version",required=True)
    parser.add_argument("--source-platform",required=True)
    parser.add_argument("--scene",required=True)
    parser.add_argument("--romfs-path",required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink() or not args.out.parent.is_dir():
            raise ValueError("new output file required")
        out=draft(args.source_original,args.source_modded,args.switch_original,
                  args.title_id,args.update_version,args.source_platform,
                  args.scene,args.romfs_path)
        args.out.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
        print("CROSS-CONSOLE GFX POSITIONS",out["relative_positions_recovered"],
              "original Switch sprite candidates, no mod image copied")
        return 0
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print("PORT BLOCKED:",exc,file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
