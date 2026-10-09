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
    "fc27_and_launcher_frametime":6,
    "sparse_JIT_dynarmic_a64_a32":5,
    "gpu_vulkan_and_compatibility":5,
    "playstation_glyphs_inside_games":6,
    "release_integrity_and_ux":4,
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
        if not isinstance(checks,list) or len(checks)!=EXPECTED[gid]:
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
