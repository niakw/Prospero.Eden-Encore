#!/usr/bin/env python3
"""Fail-closed native PS5 release/issue closure gate; read-only offline.

This check is intentionally NOT attached to CI or native build workflows.
It cannot prove test authenticity: a human must inspect the referenced
hardware captures, original game files, and library rights before promotion.
The current matrix explicitly refuses all closure (zero PS5 gates passed).
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/"docs/PS5_CLOSURE_MATRIX.json"
EXPECTED={
    "fc27_and_launcher_frametime":(
        "fc27_boots_two_sessions_fw1360",
        "fc27_first_warm_same_match_frame_time_traces",
        "fc27_no_late_oom_or_bad_alloc_under_memory_pressure",
        "fc27_stalls_shaders_cache_measured_before_after",
        "launcher_held_navigation_no_122_175ms_decode_hitches",
        "playstation_auto_popup_and_true_menu_scene_behaviour",
    ),
    "sparse_JIT_dynarmic_a64_a32":(
        "native_sdk_build_link_sparse_enabled_for_dev_experiment",
        "fw1360_executable_rw_rx_alias_4m_bootstrap_and_increment",
        "fw1360_sparse_rollback_unmap_and_memory_pressure",
        "fw1360_a64_a32_4core_real_game_execution_and_cache_flush",
        "sparse_off_fallback_and_no_regression_on_second_game",
    ),
    "gpu_vulkan_and_compatibility":(
        "native_sdk_prmt_imm_reg_compiles_and_executes",
        "prmt_pixel_correct_golden_shader_capture",
        "fermi_z0_pitch_multilayer_golden_copy_capture",
        "unsupported_prmt_fermi_semantics_not_silently_masked",
        "no_gpu_sync_queue_regression_multi_game",
    ),
    "playstation_glyphs_inside_games":(
        "legitimate_original_mod_pack_binary_source_verified",
        "title_update_romfs_sha_and_layout_qualified",
        "format_safe_BNTX_Unity_CPK_or_other_repack_roundtrip",
        "playstation_ps5_game_art_in_match_menu_hud_fc27",
        "playstation_ps5_game_art_second_game_coverage",
        "signed_versioned_opt_in_pack_delivery_and_fallback",
    ),
    "release_integrity_and_ux":(
        "complete_early_source_and_native_build_after_final_diff",
        "fw1360_reinstall_launch_exit_relaunch",
        "approved_purple_launcher_visual_review",
        "release_shipping_branch_and_rights_review",
    ),
}
TITLE_ISSUES={"playstation_glyphs_inside_games":7}
REFERENCE=re.compile(r"(?:https://github\.com/niakw/Prospero\.Eden-Encore/(?:issues|actions|commit|blob)/\S+|sha256:[0-9a-f]{64})\Z")


def audit(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("invalid closure matrix schema")
    if data.get("shipping_branch") != "fix/0.40-zbic-13.60" or \
       data.get("development_branch") != "dev/ps5-sparse-jit" or \
       data.get("approved_purple_launcher_unchanged_required") is not True or \
       data.get("shipping_unchanged_required") is not True:
        raise ValueError("protected release/approved UI contract was removed")
    workstreams=data.get("workstreams")
    if not isinstance(workstreams,list) or len(workstreams)!=len(EXPECTED):
        raise ValueError("missing or extra required workstream")
    seen=set()
    count=0
    passed=0
    blocked=[]
    for group in workstreams:
        if not isinstance(group,dict):
            raise ValueError("invalid workstream")
        gid=group.get("id")
        if gid not in EXPECTED or gid in seen:
            raise ValueError("unexpected/duplicate workstream")
        seen.add(gid)
        if group.get("issue") != TITLE_ISSUES.get(gid,8):
            raise ValueError("issue is improperly detached from required workstream")
        checks=group.get("acceptance")
        if not isinstance(checks,list) or len(checks)!=len(EXPECTED[gid]):
            raise ValueError("missing or extra acceptance evidence")
        ids=set()
        for check in checks:
            if not isinstance(check,dict):
                raise ValueError("bad acceptance item")
            key=check.get("id")
            if not isinstance(key,str) or not re.fullmatch(r"[a-z0-9_]{10,90}",key) or key in ids:
                raise ValueError("bad/repeated acceptance id")
            ids.add(key)
            count+=1
            flag=check.get("passed")
            evidence=check.get("evidence_ref")
            if type(flag) is not bool:
                raise ValueError("acceptance must be explicit boolean")
            if flag:
                if not isinstance(evidence,str) or not REFERENCE.fullmatch(evidence):
                    raise ValueError("claimed pass lacks inspectable evidence link/hash")
                passed+=1
            else:
                if evidence is not None:
                    raise ValueError("failed/untested acceptance must have no passing evidence")
                blocked.append(key)
        if ids != set(EXPECTED[gid]):
            raise ValueError("required acceptance IDs changed or an essential test removed")
        if group.get("status") not in ("blocked","ready_for_review"):
            raise ValueError("invalid workstream status")
        if any(not c["passed"] for c in checks) and group["status"]!="blocked":
            raise ValueError("prematurely ready workstream")
    if set(EXPECTED)!=seen or count!=26:
        raise ValueError("required acceptance inventory changed")
    ready=(passed==count)
    if data.get("status") != ("ready_for_human_review" if ready else "blocked"):
        raise ValueError("matrix status contradicts hardware evidence")
    return {"workstreams":len(seen),"acceptance_total":count,"passed":passed,
            "blocked":blocked,"ready_for_human_review":ready,
            "issues_to_keep_open":[7,8] if not ready else [],
            "release_automatically_approved":False,
            "manual_hardware_and_licensing_review_always_required":True}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--matrix",type=Path,default=DEFAULT)
    p.add_argument("--require-ready",action="store_true",
                   help="nonzero exit unless all 26 evidence gates passed")
    args=p.parse_args()
    try:
        if not args.matrix.is_file() or args.matrix.is_symlink() or args.matrix.stat().st_size>128*1024:
            raise ValueError("missing or unsafe closure matrix")
        data=json.loads(args.matrix.read_text("utf-8"))
        result=audit(data)
        print("EDEN_PS5_CLOSURE "+json.dumps(result,ensure_ascii=False,sort_keys=True))
        if args.require_ready and not result["ready_for_human_review"]:
            return 2
        return 0
    except (ValueError,OSError,UnicodeError) as e:
        print(f"EDEN_PS5_CLOSURE_INVALID: {e}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
