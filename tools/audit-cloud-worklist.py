#!/usr/bin/env python3
"""Inventory indexed contracts AND Encore C/C++ files outside their graph.

This is a worklist, not a semantic review or runtime qualification. Every
indexed source and authored C/C++ file receives a row with a content hash.
No file becomes HOST and no unresolved contract is closed by this command.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    module = runpy.run_path(str(ROOT / "tools/check-eden-audit-verification-matrix.py"))
    rows = module["parse_rows"](module["REGISTER"].read_text())
    contracts, stats = module["build_matrix"](
        rows, module["WORKFLOW"].read_text(), module["CATALOG"].read_text())
    tracked = set(subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")) - {""}
    # The parent index records a submodule as the `vendor` gitlink, not
    # each source file. Expand the pinned submodule index so the inventory
    # retains the original vendor/encore-active ownership and file hashes.
    if "vendor" in tracked:
        vendor_paths = subprocess.check_output(
            ["git", "-C", "vendor", "ls-files", "-z"], cwd=ROOT
        ).decode().split("\0")
        tracked.remove("vendor")  # gitlink is a directory, not a hashable file
        tracked.update("vendor/" + path for path in vendor_paths if path)
    local = set(subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=ROOT).decode().split("\0")) - {""}
    owned = {path for path in tracked
             if path.startswith(("headless/", "src/", "vendor/encore-active/"))
             and Path(path).suffix in {".h", ".hpp", ".c", ".cpp", ".inc", ".cc", ".cxx"}}
    by_path = {}
    for row in contracts:
        by_path.setdefault(row["path"], []).append(row)
    files = []
    for path in sorted(owned | by_path.keys()):
        content = (ROOT / path).read_bytes()
        linked = by_path.get(path, [])
        files.append({
            "path": path,
            "sha256": hashlib.sha256(content).hexdigest(),
            "scope": "indexed" if linked else "outside-core-contract-graph",
            "contract_ids": [r["id"] for r in linked],
            "pending_contract_ids": [r["id"] for r in linked
                                     if r["status"] in {"SOURCE", "OPEN"}],
            "p0_pending_contract_ids": [r["id"] for r in linked
                                        if r["priority"] == "P0"
                                        and r["status"] in {"SOURCE", "OPEN"}],
        })
    pending = [r for r in contracts if r["status"] in {"SOURCE", "OPEN"}]
    assert {r["path"] for r in pending} <= {r["path"] for r in files}
    assert sum(len(r["pending_contract_ids"]) for r in files) == len(pending)
    assert sum(bool(r["pending_contract_ids"]) for r in files) == stats["pending_distinct_source_paths"]
    outside = sorted(owned - by_path.keys())
    # Keep shaders, build recipes, CI, tooling, manifests and documentation
    # visible too. Immutable upstream sources/packs have separate integrity
    # gates; do not imply an Encore semantic review of those dependencies.
    supporting = []
    for path in sorted((tracked | local) - {row["path"] for row in files}):
        if path.startswith(("vendor/sources/", "vendor/objects/")):
            continue
        supporting.append({
            "path": path,
            "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
            "git_state": "tracked" if path in tracked else "untracked",
        })
    summary = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "tracked_worktree_modified": bool(subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"], cwd=ROOT, text=True).strip()),
        "indexed_contracts": len(contracts), "pending_contracts": len(pending),
        "pending_files": stats["pending_distinct_source_paths"],
        "pending_p0_files": stats["pending_p0_distinct_source_paths"],
        "owned_code_files": len(owned), "inventoried_files": len(files),
        "owned_files_outside_graph": len(outside),
        "supporting_files": len(supporting),
        "supporting_roots": dict(sorted(Counter(
            p["path"].split("/")[0] for p in supporting).items())),
        "outside_graph_roots": dict(sorted(Counter(p.split("/")[0] for p in outside).items())),
        "qualification": "inventory-only; source hashes are not behavioral or performance evidence",
    }
    if args.json:
        print(json.dumps({"summary": summary, "files": files, "contracts": contracts,
                          "supporting_files": supporting},
                         ensure_ascii=False, indent=2))
    else:
        print("ENCORE_COMPLETE_WORKLIST_PASS", json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
