#!/usr/bin/env python3
"""Per-file code progress versus proof coverage. Never infers PS5 success."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REG=ROOT/"docs/EDEN_CORE_AUDIT_DEPENDENCIES.md"
CI=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
REVIEWS=(
    "docs/EDEN_P0_SOURCE_REVIEW_2026-10-20.md",
    "docs/EDEN_P0_VULKAN_REVIEW_2026-10-20.md",
)
BASE="82c531d08641d8b28124bd2cebf37fcf85674179"
NATIVE="7ab02797110aeb260b547d299452680fb7a56bca"

def rows():
    s=REG.read_text()
    assert s.count("<!-- AUDIT_ROWS_START -->")==1
    assert s.count("<!-- AUDIT_ROWS_END -->")==1
    table=s.split("<!-- AUDIT_ROWS_START -->",1)[1].split("<!-- AUDIT_ROWS_END -->",1)[0]
    result=[]
    for line in table.splitlines():
        if not re.match(r"^\|\s*[A-Z]\d{2,3}\s*\|",line):
            continue
        cols=[x.strip() for x in line.strip().strip("|").split("|")]
        assert len(cols)==9
        ident,priority,deps,path,symbols,status,evidence,acceptance,badge=cols
        assert status in {"HOST","SOURCE","OPEN","PARKED"}
        result.append(dict(id=ident,priority=priority,path=path,
                           status=status,evidence=evidence))
    assert len(result)>=478 and len({x["id"] for x in result})==len(result)
    return result

def review_paths():
    reviewed={}
    # x60 is the backtick character delimiting paths in the review tables.
    for path in REVIEWS:
        s=(ROOT/path).read_text()
        for p in re.findall(r"^\|\s*[^|\n]+\|\s*\x60([^\x60]+)\x60\s*\|",s,re.M):
            assert p not in reviewed, ("duplicate source review",p)
            reviewed[p]=path
    assert len(reviewed)==20,("review coverage drift",len(reviewed))
    return reviewed

def diff(base):
    check=subprocess.run(["git","cat-file","-e",base+"^{commit}"],
                         cwd=ROOT,capture_output=True,check=False)
    if check.returncode: return None
    run=subprocess.run(["git","diff","--name-only",base+"..HEAD","--"],
                       cwd=ROOT,capture_output=True,text=True,check=False)
    return set(run.stdout.splitlines()) if run.returncode==0 else None

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    contracts=rows()
    reviewed=review_paths()
    owners={}
    for r in contracts: owners.setdefault(r["path"],[]).append(r)
    pending={p for p,cs in owners.items()
             if any(r["status"] in {"SOURCE","OPEN"} for r in cs)}
    p0={p for p,cs in owners.items()
        if any(r["status"] in {"SOURCE","OPEN"} and r["priority"]=="P0"
               for r in cs)}
    assert all(p in p0 for p in reviewed)
    base_delta=diff(BASE)
    native_delta=diff(NATIVE)
    categories=Counter()
    inventory=[]
    for path,cs in sorted(owners.items()):
        proofs=[]
        for r in cs:
            if r["status"] not in {"SOURCE","OPEN"}: continue
            e=r["evidence"]
            kind=("script-in-ci" if "python3 -B "+e in CI else
                  "python-not-directly-in-ci" if e.endswith(".py") else
                  "reference-not-executable")
            proofs.append(dict(id=r["id"],evidence=e,reference_kind=kind))
        if proofs:
            kinds={z["reference_kind"] for z in proofs}
            kind=("has-ci-script-reference" if "script-in-ci" in kinds else
                  "only-indirect-python" if "python-not-directly-in-ci" in kinds else
                  "only-nonexecutable")
            categories[kind]+=1
        inventory.append({
            "path":path,
            "contracts":[dict(id=r["id"],priority=r["priority"],status=r["status"]) for r in cs],
            "qualifications_pending":path in pending,
            "p0_pending":path in p0,
            "new_source_review":reviewed.get(path),
            "changed_since_base":None if base_delta is None else path in base_delta,
            "changed_since_native_package":None if native_delta is None else path in native_delta,
            "pending_proof_references":proofs,
            "code_change_needed":"unknown-without-targeted-evidence",
            "native_and_console_performance":"unverified-by-register",
        })
    assert sum(categories.values())==len(pending)
    summary={
        "contracts":len(contracts),"paths":len(owners),
        "status":dict(sorted(Counter(x["status"] for x in contracts).items())),
        "pending_paths":len(pending),"pending_p0_paths":len(p0),
        "pending_contracts":sum(x["status"] in {"SOURCE","OPEN"} for x in contracts),
        "newly_source_reviewed_p0":len(reviewed),
        "p0_not_in_these_new_review_batches":len(p0-set(reviewed)),
        "proof_reference_categories":dict(sorted(categories.items())),
        "baseline_diff_available":base_delta is not None,
        "native_diff_available":native_delta is not None,
        "pending_modified_since_base":None if base_delta is None else len(base_delta&pending),
        "code_fix_backlog":"unknown",
        "hardware_performance_proof":"not-established",
    }
    if args.json:
        print(json.dumps({"summary":summary,"files":inventory},
                         ensure_ascii=False,indent=2))
    else:
        print("ENCORE_TWO_AXIS_AUDIT_PASS",
              f"paths={len(owners)} pending={len(pending)} p0={len(p0)}",
              f"reviewed_p0={len(reviewed)}",
              f"script_refs={categories['has-ci-script-reference']}",
              f"indirect={categories['only-indirect-python']}",
              f"nonexec={categories['only-nonexecutable']}",
              f"git_base_available={base_delta is not None}",
              "code_backlog=UNKNOWN console_proof=UNVERIFIED")

if __name__=="__main__":
    main()
