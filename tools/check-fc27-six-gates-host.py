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
        "check-native-gpu-composite-syncpoint-host.py",
        "check-native-vulkan-renderer-handoff-host.py",
        "check-native-host1x-increment-handoff-host.py",
    ),
    "F06-input-and-pause": (
        "check-fc27-match-input-profile.py",
        "check-native-hid-cadence-host.py",
    ),
}

# Missing end-to-end evidence remains explicit even when all fifteen narrow
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
                if ok and script == "check-ps5-graphics-payload-preflight-host.py":
                    records = re.findall(
                        r"F01_PAYLOAD_ALLOCATION_FIXTURE prior_under_lock=(\d+) "
                        r"maintained_under_lock=(\d+) scope=host_mock", result.stdout)
                    if len(records) != 2 or records[0] != records[1]:
                        ok, reason = False, "payload_allocation_metric_missing_or_inconsistent"
                    else:
                        prior, maintained = map(int, records[0])
                        if prior != 1 or maintained != 0:
                            ok, reason = False, "payload_allocation_metric_invalid"
                        else:
                            fixture_metrics["F01_payload_allocation_host_mock"] = {
                                "prior_locked_allocator_attempts": prior,
                                "maintained_locked_allocator_attempts": maintained,
                                "scope": "guarded allocator first-use mock; NOT elapsed lock wait time",
                            }
                            print("F01_MEASURED_HOST_SUBPATH=" +
                                  json.dumps(fixture_metrics["F01_payload_allocation_host_mock"],
                                             sort_keys=True), flush=True)
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
                if ok and script == "check-native-gpu-composite-syncpoint-host.py":
                    records = re.findall(
                        r"F05_NV_DISP_GPU_SYNCPOINT_SOURCE_PASS requests=(\d+) "
                        r"delayed_and_immediate_fences=verified",
                        result.stdout)
                    not_ack = re.findall(
                        r"F05_PRESENT_ACK_NOT_PROVEN "
                        r"host_GPU_request_completion_precedes_guest_fence_callback "
                        r"-(?:O0|O2)", result.stdout)
                    if records != ["260", "260"] or len(not_ack) != 2:
                        ok, reason = False, "f05_syncpoint_source_replay_evidence_missing"
                    else:
                        fixture_metrics["F05_native_syncpoint_host"] = {
                            "requests_per_optimization": 260,
                            "compiled_modes": ["O0", "O2"],
                            "fence_ordering": "delayed_immediate_out_of_order_and_duplicate",
                            "scope": "nvdisp->GPU->Host1x native C++ host replay; "
                                     "NOT Vulkan scanout or gameplay completion",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_native_syncpoint_host"],
                                         sort_keys=True), flush=True)
                if ok and script == "check-native-vulkan-renderer-handoff-host.py":
                    records = re.findall(
                        r"F05_VULKAN_RENDER_PRESENT_HOST_PASS frames=(\d+) callbacks=(\d+) "
                        r"game_hz=30 hud_hz=60 pause_ticks=12 pool=7",
                        result.stdout)
                    bounds = re.findall(
                        r"F05_VULKAN_WSI_NOT_PROVEN real_gpu_and_scanout_unmeasured",
                        result.stdout)
                    if records != [("241", "243"), ("241", "243")] or len(bounds) != 2:
                        ok, reason = False, "f05_vulkan_present_handoff_evidence_missing"
                    else:
                        fixture_metrics["F05_vulkan_renderer_handoff_host"] = {
                            "delivered_mock_copy_frames": 241,
                            "renderer_callbacks": 243,
                            "guest_pause_ticks": 12,
                            "compiled_modes": ["O0", "O2"],
                            "scope": "real renderer and async presenter methods, mock WSI; "
                                     "NOT guest progress, native GPU or real display",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_vulkan_renderer_handoff_host"],
                                         sort_keys=True), flush=True)
                if ok and script == "check-native-host1x-increment-handoff-host.py":
                    passes = re.findall(
                        r"N04_HOST1X_INCREMENT_HANDOFF_PASS ordered=3 nested=1 "
                        r"claimed=1 pending_cancelled=1 independent=1 stress=256",
                        result.stdout)
                    negative = re.findall(
                        r"N04_HOST1X_INCREMENT_PINNED_NEGATIVE_PASS guard_blocks_callback",
                        result.stdout)
                    if len(passes) != 2 or len(negative) != 1:
                        ok, reason = False, "f05_host1x_claimed_dispatch_witness_missing"
                    else:
                        fixture_metrics["F05_host1x_increment_handoff_host"] = {
                            "stress": 256, "optimization_levels": ["O0", "O2"],
                            "scope": "native Host1x action claim, cancel and reentrance; "
                                     "NOT PS5 device-fence progress",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_host1x_increment_handoff_host"],
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
    if "F01_payload_allocation_host_mock" in fixture_metrics:
        m = fixture_metrics["F01_payload_allocation_host_mock"]
        table += ["", f"F01 guarded first-use allocator fixture: "
                       f"{m['prior_locked_allocator_attempts']} attempted allocation "
                       f"under the cache pair without preflight vs "
                       f"{m['maintained_locked_allocator_attempts']} with preflight; "
                       "NOT elapsed mutex contention time."]
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
