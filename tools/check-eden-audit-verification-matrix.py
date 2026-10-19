#!/usr/bin/env python3
"""Audit EVERY mapped Eden Encore contract without inventing native proof.

Checks per-row evidence visibility/CI execution, dependencies, ownership
and the remaining qualification backlog. The existing audit-register,
source-inventory and source-parity checks are independent companion gates.

--json emits every graph row with its exact proof limits for review.
This audit never builds a game, marks SOURCE as HOST, or times PS5 frames.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs/EDEN_CORE_AUDIT_DEPENDENCIES.md"
WORKFLOW = ROOT / ".github/workflows/encore-core-preflight.yml"
CATALOG = ROOT / "docs/EDEN_ACTIVE_SOURCE_CATALOG.md"
SOURCE_ROOT = ROOT / "vendor/encore-active"

LANES = {
    "B": "build", "Q": "native-lifecycle", "D": "dma",
    "V": "vulkan", "J": "jit-cpu", "H": "hle-scheduler",
    "M": "guest-memory", "S": "frame-progress",
    "T": "platform", "N": "gpu-nvdrv", "A": "audio",
    "F": "filesystem", "R": "radv", "U": "application-headers",
    "L": "launch-resources", "W": "network"
}
STATES = {
    "HOST": "specific-host-property-only",
    "SOURCE": "source-reviewed-not-runtime-qualified",
    "OPEN": "unresolved-behavior-or-ownership",
    "PARKED": "experiment-not-authorized-for-runtime"
}


def parse_rows(source: str) -> list[dict]:
    begin = "<!-- AUDIT_ROWS_START -->"
    end = "<!-- AUDIT_ROWS_END -->"
    assert source.count(begin) == source.count(end) == 1
    section = source.split(begin, 1)[1].split(end, 1)[0]
    rows = []
    for raw in section.splitlines():
        if not re.match(r"^\\|\\s*[A-Z][0-9]{2,3}\\s*\\|", raw):
            continue
        fields = [cell.strip() for cell in raw.strip().strip("|").split("|")]
        assert len(fields) == 9, ("malformed contract", raw[:120])
        key, priority, deps, path, symbols, status, evidence, acceptance, badge = fields
        assert re.fullmatch(r"[A-Z][0-9]{2,3}", key), key
        assert priority in {"P0", "P1", "P2"}, key
        assert status in STATES, key
        assert key[0] in LANES, key
        assert evidence and path and symbols and acceptance and badge, key
        rows.append({
            "id": key, "priority": priority,
            "prerequisites": [] if deps == "-" else [x.strip() for x in deps.split(",")],
            "path": path, "symbols": [x.strip() for x in symbols.split(";")],
            "status": status, "evidence": evidence, "acceptance": acceptance,
            "lane": LANES[key[0]],
        })
    assert len(rows) >= 477, ("lost previously indexed contracts", len(rows))
    return rows


def build_matrix(rows: list[dict], workflow: str, catalog: str) -> tuple[list[dict], dict]:
    keyed = {r["id"]: r for r in rows}
    assert len(keyed) == len(rows), "duplicate contract IDs"
    assert all(x["symbols"] and all(x["symbols"]) for x in rows)
    accounted = 0
    for row in rows:
        assert all(p in keyed and p != row["id"] for p in row["prerequisites"]), row["id"]
        evidence_file = ROOT / row["evidence"]
        source_file = ROOT / row["path"]
        assert evidence_file.is_file(), (row["id"], "missing evidence")
        assert source_file.is_file(), (row["id"], "missing source")
        # Do not trust the symbol list without rechecking the original source.
        text = source_file.read_text()
        for symbol in row["symbols"]:
            assert symbol in text, (row["id"], row["path"], symbol)
        path = row["path"]
        if path.startswith("vendor/encore-active/"):
            rel = path.removeprefix("vendor/encore-active/")
            assert ("| \`" + rel + "\` |") in catalog, (row["id"], "missing active catalogue owner", rel)
            owner = "encore-active"
        elif path.startswith("vendor/sources/"):
            owner = "pinned-reference"
        elif path.startswith("headless/"):
            owner = "app-or-native-integration"
        else:
            owner = "docs-or-tools"
        script = row["evidence"].endswith(".py")
        direct = script and ("python3 -B " + row["evidence"]) in workflow
        if row["status"] == "HOST":
            # A passed specific host witness does NOT establish native results.
            assert script and direct, (row["id"], "host proof not in CI")
        row["owner_class"] = owner
        row["evidence_kind"] = ("python-in-preflight" if direct else
                                "python-not-directly-in-preflight" if script else
                                "reference-not-executable")
        row["proof_level"] = STATES[row["status"]]
        row["native_game_validation"] = False
        row["measured_frametime_improvement"] = False
        row["needs_runtime_evidence"] = row["status"] in {"HOST", "SOURCE", "OPEN"}
        row["qualification_blocked"] = row["status"] == "PARKED"
        accounted += 1
    assert accounted == len(rows)
    # Verify any dependency chain leading from a P0 contract to a suspended
    # experimental unit; those cannot be silently marked production-ready.
    def transitive_deps(ident: str, visited: set[str] | None = None) -> set[str]:
        if visited is None:
            visited = set()
        for dep in keyed[ident]["prerequisites"]:
            if dep not in visited:
                visited.add(dep)
                transitive_deps(dep, visited)
        return visited
    for row in rows:
        blocked = sorted(d for d in transitive_deps(row["id"])
                         if keyed[d]["status"] == "PARKED")
        row["parked_prerequisites"] = blocked
        if row["priority"] == "P0" and row["status"] != "PARKED":
            assert not blocked, (row["id"], "P0 transitively requires PARKED experiment", blocked)

    statuses = Counter(r["status"] for r in rows)
    priorities = Counter(r["priority"] for r in rows)
    lane_counts: dict[str, dict] = {}
    for row in rows:
        lane = row["lane"]
        if lane not in lane_counts:
            lane_counts[lane] = {"total": 0, "host": 0, "open": 0,
                                 "pending_p0": 0, "pending": 0}
        lane_counts[lane]["total"] += 1
        lane_counts[lane]["host"] += row["status"] == "HOST"
        lane_counts[lane]["open"] += row["status"] == "OPEN"
        lane_counts[lane]["pending"] += row["status"] in {"SOURCE", "OPEN"}
        lane_counts[lane]["pending_p0"] += (
            row["priority"] == "P0" and row["status"] in {"SOURCE", "OPEN"})
    direct = sum(r["evidence_kind"] == "python-in-preflight" for r in rows)
    indirect = [r for r in rows
                if r["evidence_kind"] == "python-not-directly-in-preflight"]
    undirect = sorted(set(r["evidence"] for r in indirect))
    assert sum(statuses.values()) == len(rows)
    assert statuses["HOST"] == 33, "HOST claims changed: review evidence before modifying guard"
    assert all(r["status"] != "HOST" for r in indirect)
    assert not any(r["native_game_validation"] or r["measured_frametime_improvement"]
                   for r in rows), "host coverage cannot certify console performance"
    stats = {
        "contracts": len(rows),
        "distinct_source_paths": len({r["path"] for r in rows}),
        "symbol_anchors": sum(len(r["symbols"]) for r in rows),
        "status": dict(sorted(statuses.items())),
        "priority": dict(sorted(priorities.items())),
        "pending_source_or_open": statuses["SOURCE"] + statuses["OPEN"],
        "pending_p0": sum(r["priority"] == "P0" and
                          r["status"] in {"SOURCE", "OPEN"} for r in rows),
        "script_references_direct_in_preflight": direct,
        "script_references_not_direct_in_preflight": len(indirect),
        "non_direct_script_paths": undirect,
        "reference_only_rows": sum(r["evidence_kind"] == "reference-not-executable"
                                   for r in rows),
        "lane_coverage": dict(sorted(lane_counts.items())),
        "native_console_performance_certificates": 0,
        "scope": "indexed graph only; no exhaustive all-functions optimization guarantee",
    }
    # An independent summary must equal the original register, not quietly
    # supersede the existing numeric contract.
    assert f"| Graphe connu | {stats['contracts']} | " in REGISTER.read_text()
    return rows, stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true",
                        help="emit all contracts and their individual proof state")
    args = parser.parse_args()
    rows = parse_rows(REGISTER.read_text())
    matrix, stats = build_matrix(rows, WORKFLOW.read_text(), CATALOG.read_text())
    if args.json:
        print(json.dumps({"summary": stats, "contracts": matrix},
                         ensure_ascii=False, indent=2))
    else:
        print("ENCORE_AUDIT_VERIFICATION_MATRIX_PASS",
              f"contracts={stats['contracts']}",
              f"paths={stats['distinct_source_paths']}",
              f"anchors={stats['symbol_anchors']}",
              f"host={stats['status']['HOST']}",
              f"pending={stats['pending_source_or_open']}",
              f"p0_pending={stats['pending_p0']}",
              f"direct_script_references={stats['script_references_direct_in_preflight']}",
              f"indirect_script_references={stats['script_references_not_direct_in_preflight']}",
              "native_proof=0")


if __name__ == "__main__":
    main()
