#!/usr/bin/env python3
"""Independently exercise six native FC27 technical *subpaths* on host.

These are existing source-extracted C++/UBSan witnesses, not proof that any
F01-F06 exit gate has closed. Continue after a failure so an early broken
generator/audit does not hide unrelated GPU, JIT, HLE or HID results.
No emulator, synthetic screenshots, firmware, network or console required.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GROUPS: dict[str, tuple[str, ...]] = {
    "F01-cache-contention": (
        "check-ps5-graphics-payload-preflight-host.py",
        "check-ps5-consecutive-sampler-reuse-host.py",
    ),
    "F02-jit-invalidation": (
        "check-native-jit-invalidation-snapshot-host.py",
        "check-native-jit-code-space-bounds-host.py",
    ),
    "F03-hud-freshness": (
        "check-ps5-texture-channel-missing-mapping-host.py",
        "check-native-hardware-composer-liveness-host.py",
    ),
    "F04-texture-integrity": (
        "check-ps5-scissor-extremes-host.py",
        "check-ps5-buffer-region-multipage-host.py",
    ),
    "F05-guest-progress": (
        "check-surface-lifecycle.py",
        "check-native-nvnflinger-detach-wake-host.py",
    ),
    "F06-input-and-pause": (
        "check-fc27-match-input-profile.py",
        "check-native-hid-cadence-host.py",
    ),
}

# Missing end-to-end evidence remains explicit even when all twelve narrow
# host probes succeed. Neither a successful tool run nor a source checksum is
# a measured frame-latency improvement or a complete technical exit proof.
UNPROVEN_EXIT_EVIDENCE = {
    "F01-cache-contention": "same-workload contention/critical-section latency before-after, native selection",
    "F02-jit-invalidation": "per-core cold/repeat compilation and invalidation before-after, native selection",
    "F03-hud-freshness": "TIC/TSC -> view -> descriptor -> barrier -> present freshness replay",
    "F04-texture-integrity": "alias/remap -> DMA/upload -> byte-content integrity replay",
    "F05-guest-progress": "HID/HLE/IPC -> buffer queue -> fence -> present deterministic liveness replay",
    "F06-input-and-pause": "custom mapping and pause/half-time/end transition end-to-end replay",
}

def run() -> int:
    status = {}
    fixture_metrics = {}
    for gate, scripts in GROUPS.items():
        checks = []
        for script in scripts:
            path = ROOT / "tools" / script
            if not path.is_file():
                checks.append({"script": script, "ok": False, "reason": "absent"})
                continue
            try:
                result = subprocess.run(
                    [sys.executable, "-B", str(path)],
                    cwd=ROOT, capture_output=True, text=True, timeout=180,
                )
                ok = result.returncode == 0
                reason = "" if ok else f"exit={result.returncode}"
                if ok and script == "check-ps5-consecutive-sampler-reuse-host.py":
                    # Parse numbers emitted by executed source-extracted C++
                    # at O0/O2: never report hardcoded optimization percentages.
                    records = re.findall(
                        r"F01_SAMPLER_LOOKUP_FIXTURE descriptors=(\d+) "
                        r"reference_calls=(\d+) maintained_calls=(\d+) "
                        r"avoided_calls=(\d+) scope=host_mock", result.stdout)
                    if len(records) != 2 or records[0] != records[1]:
                        ok, reason = False, "sampler_fixture_metric_missing_or_inconsistent"
                    else:
                        total, ref, current, avoided = map(int, records[0])
                        if not (0 < current <= ref == total and ref - current == avoided):
                            ok, reason = False, "sampler_fixture_metric_invalid"
                        else:
                            fixture_metrics["F01_sampler_lookup_host_mock"] = {
                                "descriptors": total, "reference_calls": ref,
                                "maintained_calls": current, "avoided_calls": avoided,
                                "scope": "mocked lookup count; NOT mutex latency or FC27 performance",
                            }
                            print("F01_MEASURED_HOST_SUBPATH=" +
                                  json.dumps(fixture_metrics["F01_sampler_lookup_host_mock"],
                                             sort_keys=True), flush=True)
                checks.append({"script": script, "ok": ok, "reason": reason})
                if not ok:
                    print(f"FAIL {gate} {script}", flush=True)
                    print((result.stdout + "\n" + result.stderr)[-6000:], flush=True)
            except subprocess.TimeoutExpired:
                checks.append({"script": script, "ok": False, "reason": "timeout"})
                print(f"FAIL {gate} {script} timed out", flush=True)
        status[gate] = checks
        print(f"{gate}: " +
              ("HOST_SUBPATH_PASS" if all(x["ok"] for x in checks)
               else "HOST_SUBPATH_FAIL"), flush=True)
    summary = {"scope": "HOST_SOURCE_EXTRACTED_ONLY",
               "f01_to_f06_closed": 0, "console_qualified": False,
               "host_subpaths_passed": sum(c["ok"] for cs in status.values() for c in cs),
               "host_subpaths_total": sum(len(cs) for cs in status.values()),
               "fixture_metrics": fixture_metrics,
               "unproven_exit_evidence": UNPROVEN_EXIT_EVIDENCE,
               "gates": status}
    print("FC27_SIX_GATES_HOST_CHECKPOINT=" +
          json.dumps(summary, ensure_ascii=True, separators=(",", ":")), flush=True)
    table = ["## FC27 F01-F06 — host checkpoint (NOT gameplay qualification)",
             "| Criterion | Source-derived witnesses |", "| --- | --- |"]
    for gate, checks in status.items():
        label = "PASS" if all(x["ok"] for x in checks) else "FAIL"
        table.append(f"| {gate} | {label} ({sum(x['ok'] for x in checks)}/{len(checks)}) |")
    table += ["", "0/6 technical exit criteria certified by this checkpoint; "
                    "native packaging and PS5 in-game evidence are separate.",
              "", "#### Critical unproven exit evidence"]
    for gate, missing in UNPROVEN_EXIT_EVIDENCE.items():
        table.append(f"- {gate}: {missing}")
    if "F01_sampler_lookup_host_mock" in fixture_metrics:
        m = fixture_metrics["F01_sampler_lookup_host_mock"]
        table += ["", f"Measured narrow F01 fixture: {m['reference_calls']} direct "
                       f"sampler lookups vs {m['maintained_calls']} maintained "
                       f"lookups on {m['descriptors']} descriptors; "
                       "NOT a lock-time or FPS improvement."]
    if target := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(target, "a", encoding="utf-8") as output:
            output.write("\n".join(table) + "\n")
    return int(any(not x["ok"] for checks in status.values() for x in checks))

if __name__ == "__main__":
    sys.exit(run())
