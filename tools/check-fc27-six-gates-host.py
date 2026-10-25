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
        "check-native-jit-invalidation-lock-budget-host.py",
        "check-native-jit-cold-repeat-host.py",
    ),
    "F03-hud-freshness": (
        "check-ps5-texture-channel-missing-mapping-host.py",
        "check-fc27-f03-native-texture-feedback-chain-host.py",
        "check-fc27-f03-native-present-freshness-host.py",
        "check-native-hardware-composer-liveness-host.py",
    ),
    "F04-texture-integrity": (
        "check-fc27-f04-native-dma-alias-bytes-host.py",
        "check-fc27-f04-native-upload-revision-host.py",
        "check-fc27-f04-native-vulkan-upload-barriers-host.py",
        "check-fc27-f04-native-remap-dma-upload-chain-host.py",
        "check-ps5-scissor-extremes-host.py",
        "check-ps5-buffer-region-multipage-host.py",
    ),
    "F05-guest-progress": (
        "check-surface-lifecycle.py",
        "check-native-nvnflinger-detach-wake-host.py",
        "check-native-gpu-composite-syncpoint-host.py",
        "check-native-vulkan-renderer-handoff-host.py",
        "check-fc27-f05-native-nvdisp-vulkan-present-chain-host.py",
        "check-fc27-f05-producer-release-wake-host.py",
        "check-fc27-f05-native-consumer-disconnect-host.py",
        "check-fc27-f05-native-acquire-drop-wake-host.py",
        "check-fc27-f05-native-queue-replace-wake-host.py",
        "check-fc27-f05-native-kernel-wait-publication-host.py",
        "check-fc27-f05-native-kthread-endwait-host.py",
        "check-fc27-f05-native-binder-handle-ipc-host.py",
        "check-native-nvnflinger-dequeue-profile-host.py",
        "check-native-host1x-increment-handoff-host.py",
    ),
    "F06-input-and-pause": (
        "check-fc27-match-input-profile.py",
        "check-native-hid-cadence-host.py",
        "check-fc27-f06-native-pad-transition-host.py",
        "check-fc27-f06-native-npad-handoff-host.py",
        "check-fc27-f06-native-npad-lifo-host.py",
    ),
}

# Missing end-to-end evidence remains explicit even when all seventeen narrow
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
                if ok and script == "check-ps5-consecutive-sampler-reuse-host.py":
                    # F01 only: before/after identical descriptor source loop,
                    # paired lock with real contention, synthetic lookup cost.
                    # Accept a PRE-CONSOLE technical closure, NEVER FPS proof.
                    budget = re.findall(
                        r"F01_NATIVE_SOURCE_LOCK_BUDGET draws=(\d+) descriptors=(\d+) "
                        r"prior_calls=(\d+) maintained_calls=(\d+) "
                        r"prior_held_ns=(\d+) maintained_held_ns=(\d+) "
                        r"prior_wait_ns=(\d+) maintained_wait_ns=(\d+) "
                        r"scope=host_synthetic_lookup_and_real_contender",
                        result.stdout)
                    selection = re.findall(
                        r"F01_NATIVE_SELECTION_SOURCE_PASS ps5_real_latency_unmeasured",
                        result.stdout)
                    if (len(budget) != 2 or len(selection) != 2 or
                            any((int(m[0]),int(m[1]),int(m[2]),int(m[3]))
                                != (2048,7,14336,4096) for m in budget) or
                            any(int(m[5])*10 >= int(m[4])*9
                                or int(m[4]) <= 0 for m in budget)):
                        ok, reason = False, "f01_source_lock_budget_missing_or_not_improved"
                    else:
                        fixture_metrics["F01_native_lock_budget_host"] = {
                            "draws": 2048, "descriptors_per_draw": 7,
                            "lookup_calls_before": 14336,
                            "lookup_calls_after": 4096,
                            "O0_before_lock_ns": int(budget[0][4]),
                            "O0_after_lock_ns": int(budget[0][5]),
                            "O2_before_lock_ns": int(budget[1][4]),
                            "O2_after_lock_ns": int(budget[1][5]),
                            "O0_before_wait_ns": int(budget[0][6]),
                            "O0_after_wait_ns": int(budget[0][7]),
                            "O2_before_wait_ns": int(budget[1][6]),
                            "O2_after_wait_ns": int(budget[1][7]),
                            "scope": "source-extracted C++ loops, controlled mock lookup "
                                     "and real competing mutex; native CMake owner selected. "
                                     "NOT guest FC27 FPS or real driver mutex timings",
                        }
                        print("F01_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F01_native_lock_budget_host"],
                                         sort_keys=True), flush=True)
                if ok and script == "check-native-jit-cold-repeat-host.py":
                    found = re.findall(
                        r"F02_JIT_NATIVE_COLD_REPLAY_PASS arch=(A32|A64) "
                        r"impl=(pinned|maintained) cold=(\d+) repeated_hits=(\d+) "
                        r"recompile=(\d+) full_clear_compile=(\d+) "
                        r"total_emissions=(\d+) isolated_cores=(\d+) cold_total_ns=(\d+) "
                        r"hot_total_ns=(\d+) "
                        r"scope=source_extracted_synthetic_translator", result.stdout)
                    counts = {}
                    for arch, kind, cold, hits, recompile, cleared, emissions, isolated, cold_ns, hot_ns in found:
                        counts.setdefault((arch, kind), []).append(
                            (int(cold), int(hits), int(recompile), int(cleared),
                             int(emissions), int(isolated), int(cold_ns), int(hot_ns)))
                    desired = {(arch, kind) for arch in ("A32","A64")
                               for kind in ("pinned","maintained")}
                    if (set(counts) != desired or
                            any(len(series) != 2 for series in counts.values()) or
                            any(values[:6] != (32, 512, 8, 32, 72, 2) or
                                min(values[6:]) <= 0
                                for series in counts.values() for values in series)):
                        ok, reason = False, "f02_cold_repeat_invalidations_evidence_missing"
                    else:
                        fixture_metrics["F02_cold_repeat_source_host"] = {
                            arch: {kind: [
                                {"cold_ns": x[6], "hot_ns": x[7]} for x in counts[(arch,kind)]]
                                for kind in ("pinned","maintained")}
                            for arch in ("A32","A64")
                        }
                        fixture_metrics["F02_cold_repeat_source_host"]["scope"] = (
                            "executed pinned and selected GetBlock methods with mock emitter, "
                            "not real guest JIT compilation or PS5 FPS")
                        print("F02_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F02_cold_repeat_source_host"],
                                         sort_keys=True),flush=True)
                if ok and script == "check-native-jit-invalidation-lock-budget-host.py":
                    records = re.findall(
                        r"F02_JIT_NATIVE_INVALIDATION_BUDGET_PASS "
                        r"arch=(A32|A64) impl=(pinned|maintained) "
                        r"range_drains=(\d+) empty_repeats=(\d+) "
                        r"held_lock_ns=(\d+) pinned_dispatch_under_guard=(0|1) "
                        r"scope=source_extracted_synthetic_emitter", result.stdout)
                    expected = {(arch, impl) for arch in ("A32", "A64")
                                for impl in ("pinned", "maintained")}
                    groups = {}
                    for arch, impl, drained, repeats, held, guarded in records:
                        groups.setdefault((arch, impl), []).append(
                            (int(drained), int(repeats), int(held), int(guarded)))
                    if set(groups) != expected or any(len(v) != 2 for v in groups.values()):
                        ok, reason = False, "f02_jit_invalidation_budget_missing"
                    else:
                        for arch in ("A32", "A64"):
                            baseline = groups[(arch, "pinned")]
                            maintained = groups[(arch, "maintained")]
                            if (any(x[0] != 96 or x[1] != 96 or x[2] <= 0 for x in baseline + maintained)
                                    or any(x[3] != 1 for x in baseline)
                                    or any(x[3] != 0 for x in maintained)):
                                ok, reason = False, "f02_lock_dispatch_or_drain_regression"
                                break
                        if ok:
                            fixture_metrics["F02_native_invalidation_lock_host"] = {
                                "a32": {variant: [x[2] for x in groups[("A32", variant)]]
                                        for variant in ("pinned", "maintained")},
                                "a64": {variant: [x[2] for x in groups[("A64", variant)]]
                                        for variant in ("pinned", "maintained")},
                                "range_drains": 96,
                                "empty_repeated_drains": 96,
                                "scope": "pinned/maintained C++ invalidation and mock emitter; "
                                         "NOT cold compilation timing, guest behavior, or PS5 FPS",
                            }
                            print("F02_MEASURED_HOST_SUBPATH=" +
                                  json.dumps(fixture_metrics["F02_native_invalidation_lock_host"],
                                             sort_keys=True), flush=True)
                if ok and script == "check-fc27-f03-native-texture-feedback-chain-host.py":
                    actual = re.findall(
                        r"F03_NATIVE_TIC_DESCRIPTOR_BARRIER_CHAIN_PASS "
                        r"frames=(\d+) transient_recoveries=(\d+) "
                        r"remapped_recoveries=(\d+) sampler_lookups=(\d+) "
                        r"barriers=(\d+) native_functions=(\d+) "
                        r"scope=source_extracted_host_no_gpu_present",result.stdout)
                    if (len(actual) != 2 or
                            any(tuple(map(int,m)) != (60,1,1,1,63,3)
                                for m in actual)):
                        ok,reason = False,"f03_integrated_texture_feedback_proof_missing"
                    else:
                        fixture_metrics["F03_tic_descriptor_feedback_host"] = {
                            "hud_frames":60,"transient_recoveries":1,
                            "remap_recoveries":1,"native_bound_descriptor_loops":2,
                            "feedback_barrier_calls":63,
                            "compile_modes":["O0","O2"],
                            "scope":"selected TIC/TSC cache, view map, graphic loop, "
                                    "feedback barrier. No Vulkan submit/fence/present.",
                        }
                        print("F03_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F03_tic_descriptor_feedback_host"],
                                         sort_keys=True),flush=True)
                if ok and script == "check-fc27-f03-native-present-freshness-host.py":
                    replays = re.findall(
                        r"F03_NATIVE_TIC_TO_PRESENT_FRESHNESS_PASS "
                        r"frames=(\d+) hud_unique=(\d+) remaps=(\d+) "
                        r"transient_missing=(\d+) pause_ticks=(\d+) barriers=(\d+) "
                        r"source_sections=(\d+) "
                        r"scope=source_extracted_host_mock_gpu", result.stdout)
                    if (len(replays) != 2 or
                            any(tuple(map(int,m)) != (241,241,2,1,12,241,9)
                                for m in replays)):
                        ok,reason=False,"f03_native_present_freshness_missing"
                    else:
                        fixture_metrics["F03_texture_to_present_host"] = {
                            "rendered_frames":241,"distinct_hud_content_revisions":241,
                            "remaps":2,"transient_missing_recoveries":1,
                            "paused_game_ticks":12,
                            "feedback_barriers":241,"compile_modes":["O0","O2"],
                            "scope":"real selected native TIC/view/descriptor/barrier and "
                                    "renderer/present-manager methods with mocked GPU and "
                                    "HUD revision content; NOT device pixels or WSI scanout",
                        }
                        print("F03_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F03_texture_to_present_host"],
                                         sort_keys=True),flush=True)
                if ok and script == "check-fc27-f04-native-remap-dma-upload-chain-host.py":
                    # The same executable combines source-selected GPU unmap,
                    # MaxwellDMA, cache invalidation, alias ordering and image
                    # staging. Require the full numeric witness at O0 and O2;
                    # a green narrow fixture without this record is NOT exit.
                    matches = re.findall(
                        r"F04_NATIVE_REMAP_DMA_UPLOAD_CHAIN_PASS "
                        r"dma_copies=(\d+) alias_copies=(\d+) remaps=(\d+) "
                        r"revisions=(\d+) barriers=(\d+) "
                        r"scope=source_extracted_host_mock_address_rebind_and_gpu_bytes",
                        result.stdout,
                    )
                    modes = re.findall(
                        r"F04_NATIVE_TEXTURE_UPLOAD_REVISION_PASS[^\n]*"
                        r"\s-(O0|O2)", result.stdout)
                    excluded = (
                        "F04_REAL_VULKAN_PIXELS_AND_GPU_ADDRESS_REBIND_UNVERIFIED"
                        in result.stdout
                    )
                    if (len(matches) != 2 or
                            any(tuple(map(int,values)) != (3,2,1,3,3)
                                for values in matches) or
                            modes != ["O0","O2"] or not excluded):
                        ok, reason = False, "f04_native_chain_metrics_missing_or_invalid"
                    else:
                        fixture_metrics["F04_native_remap_dma_upload_host"] = {
                            "dma_copies": 3,
                            "alias_copies": 2,
                            "gpu_unmaps": 1,
                            "content_revisions": 3,
                            "upload_barriers": 3,
                            "compile_modes": ["O0","O2"],
                            "scope": "selected MaxwellDMA pitch, GPU image-unmap, "
                                     "CPU cache invalidation, alias sorting and "
                                     "Vulkan texture-refresh C++ in ONE replay. "
                                     "GPU-address rebind, Vulkan upload execution "
                                     "and guest image/pixels are host-mocked.",
                        }
                        print("F04_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F04_native_remap_dma_upload_host"],
                                         sort_keys=True), flush=True)
                if ok and script == "check-native-nvnflinger-dequeue-profile-host.py":
                    native_waits = re.findall(
                        r"^profile=([01]) (-O[02]) "
                        r"F05_NATIVE_DEQUEUE_CONDITION_INFLIGHT_PASS waiters=(\d+) "
                        r"active_gauge_correct=(\d+) restored=(\d+) disabled_quiet=(\d+) "
                        r"scope=source_extracted_native_condvar$",
                        result.stdout, re.MULTILINE,
                    )
                    scopes = re.findall(
                        r"^(-O[02]) F05_ACTIVE_DEQUEUE_BLOCKERS_PASS blocked=(\d+) "
                        r"cleared=(\d+) disabled_quiet=(\d+) scope=source_extracted$",
                        result.stdout, re.MULTILINE,
                    )
                    prior_probe = re.findall(
                        r"^NATIVE_NVN_DEQUEUE_PROFILE_PASS (dev|release) (-O[02])$",
                        result.stdout, re.MULTILINE,
                    )
                    excludes = "F05_CONDITION_WAITER_HOST_ONLY_NOT_GUEST_IPC_OR_FC27_PROGRESS" in result.stdout
                    expected_modes = [
                        ("0", "-O0", "8", "1", "1", "1"),
                        ("0", "-O2", "8", "1", "1", "1"),
                        ("1", "-O0", "8", "1", "1", "1"),
                        ("1", "-O2", "8", "1", "1", "1"),
                    ]
                    if (native_waits != expected_modes or scopes != [
                        ("-O0","8","1","1"), ("-O2","8","1","1"),
                    ] or prior_probe != [
                        ("release","-O0"), ("release","-O2"),
                        ("dev","-O0"), ("dev","-O2"),
                    ] or not excludes):
                        ok, reason = False, "f05_native_dequeue_inflight_profile_witness_missing"
                    else:
                        fixture_metrics["F05_native_dequeue_inflight_host"] = {
                            "concurrent_native_waiters": 8,
                            "profile_enabled": True,
                            "release_path_no_counter": True,
                            "profile_off_no_counter": True,
                            "scope_clears_on_release": True,
                            "compile_modes": ["O0","O2"],
                            "scope": "source-extracted maintained BufferQueueCore condvar and "
                                     "selected producer blocking scope, mock host waiters; "
                                     "no guest thread PC or FC27 liveness proof",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_native_dequeue_inflight_host"],
                                         sort_keys=True), flush=True)

                if ok and script == "check-fc27-f05-native-binder-handle-ipc-host.py":
                    binder_handle = re.findall(
                        r"F05_NATIVE_BINDER_HANDLE_IPC_PASS cycles=(\d+) "
                        r"copied_handle_identity=(\d+) unknown_binder_rejected=(\d+) "
                        r"level_coalescing=(\d+) reset_rearm=(\d+) "
                        r"same_event_across_copies=(\d+) stopped_callback_quiet=(\d+) "
                        r"scope=shipping_binder_ipc_and_producer_methods_mock_handle_table",
                        result.stdout,
                    )
                    excluded = ("F05_REAL_HIPC_DISPATCH_GUEST_WAIT_AND_FC27_PROGRESS_NOT_PROVEN"
                                in result.stdout)
                    if binder_handle != [("260","1","1","1","260","1","1")]*2 or not excluded:
                        ok, reason = False, "f05_binder_handle_ipc_event_identity_missing"
                    else:
                        fixture_metrics["F05_binder_native_handle_ipc_host"] = {
                            "event_cycles": 260,
                            "same_copy_handle": True,
                            "unknown_binder_rejected": True,
                            "level_coalescing": True,
                            "reset_rearm": 260,
                            "compile_modes": ["O0", "O2"],
                            "scope": "source-extracted IHOSBinderDriver and BufferQueueProducer "
                                     "GetNativeHandle; mocked handle table, no real HIPC dispatch",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_binder_native_handle_ipc_host"],
                                         sort_keys=True), flush=True)

                if ok and script == "check-fc27-f05-native-kthread-endwait-host.py":
                    guest_endwait = re.findall(
                        r"F05_NATIVE_KTHREAD_ENDWAIT_PASS cycles=(\d+) resumed_game=(\d+) "
                        r"resumed_hud=(\d+) wait_nodes_unlinked=(\d+) runnable_state=(\d+) "
                        r"timer_cancelled=(\d+) level_coalescing=(\d+) safe_stop=(\d+) "
                        r"scope=source_extracted_kthread_queue_mock_scheduler",
                        result.stdout,
                    )
                    integrated_release = re.findall(
                        r"F05_NATIVE_RELEASE_TO_KTHREAD_PASS cycles=(\\d+) "
                        r"successful_releases=(\\d+) stale_releases_quiet=(\\d+) "
                        r"duplicate_releases_quiet=(\\d+) guest_wait_completions=(\\d+) "
                        r"host_dequeue_generations=(\\d+) "
                        r"scope=source_extracted_consumer_release_and_kthread_mock_scheduler",
                        result.stdout,
                    )
                    excludes = "F05_REAL_GUEST_SCHEDULER_AND_FC27_LIVENESS_NOT_PROVEN" in result.stdout
                    if (guest_endwait != [("260","260","260","1","1","520","1","1")]*2
                            or integrated_release != [("260","260","260","260","520","260")]*2
                            or not excludes):
                        ok, reason = False, "f05_native_guest_kthread_endwait_witness_missing"
                    else:
                        fixture_metrics["F05_native_kthread_endwait_host"] = {
                            "wait_cycles": 260,
                            "guest_style_threads": 2,
                            "native_guest_resume_transitions": 520,
                            "consumer_successful_releases": 260,
                            "stale_and_duplicate_releases_quiet": True,
                            "native_consumer_to_kthread_chain": True,
                            "wait_nodes_unlinked": True,
                            "timer_tasks_cancelled": 520,
                            "compile_modes": ["O0", "O2"],
                            "scope": "source-extracted native KThread::NotifyAvailable, "
                                     "KThreadQueue::EndWait and native kernel event chain; "
                                     "mock scheduler, no real guest execution or FC27 evidence",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_native_kthread_endwait_host"],
                                         sort_keys=True), flush=True)

                if ok and script == "check-fc27-f05-native-kernel-wait-publication-host.py":
                    kernel_waits = re.findall(
                        r"F05_NATIVE_KERNEL_GUEST_WAIT_WAKE_PASS cycles=(\d+) "
                        r"mock_guest_threads=(\d+) resumptions=(\d+) "
                        r"coalesced_signals=(\d+) reset_rearms=(\d+) "
                        r"safe_stop=(\d+) scope=shipping_event_methods_mock_scheduler",
                        result.stdout,
                    )
                    excludes = (
                        "F05_NATIVE_GUEST_KTHREAD_ENDWAIT_AND_FC27_LIVENESS_NOT_PROVEN"
                        in result.stdout
                    )
                    if kernel_waits != [("260","2","520","260","260","1")]*2 or not excludes:
                        ok, reason = False, "f05_kernel_readable_mock_guest_wait_missing"
                    else:
                        fixture_metrics["F05_kernel_readable_wait_host"] = {
                            "guest_style_waiter_threads": 2,
                            "resumptions": 520,
                            "event_cycles": 260,
                            "level_signal_coalescing": 260,
                            "reset_rearms": 260,
                            "compile_modes": ["O0", "O2"],
                            "scope": "native KEvent/KReadableEvent/KSynchronizationObject "
                                     "C++ plus mocked KThread and kernel scheduler; "
                                     "real guest EndWait and FC27 progress unproven",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_kernel_readable_wait_host"],
                                         sort_keys=True), flush=True)

                if ok and script == "check-fc27-f05-native-queue-replace-wake-host.py":
                    queue_releases = re.findall(
                        r"F05_NATIVE_QUEUE_REPLACEMENT_GUEST_WAKE_PASS replacements=(\d+) "
                        r"tracked_release_signal=(\d+) untracked_quiet=(\d+) "
                        r"regular_enqueue_quiet=(\d+) callback_unlocked=(\d+) "
                        r"scope=source_extracted_mock_guest_event",
                        result.stdout,
                    )
                    outside = ("F05_HIPC_SCHEDULING_AND_FC27_FRAME_PROGRESS_NOT_PROVEN"
                               in result.stdout)
                    if queue_releases != [("260", "1", "1", "1", "1")]*2 or not outside:
                        ok, reason = False, "f05_queue_replacement_guest_wake_witness_missing"
                    else:
                        fixture_metrics["F05_native_queue_replacement_guest_wake_host"] = {
                            "replacements": 260,
                            "guest_event_on_tracked_drop": True,
                            "no_event_on_untracked_replace": True,
                            "no_event_on_ordinary_enqueue": True,
                            "binder_callback_after_core_mutex": True,
                            "compile_modes": ["O0", "O2"],
                            "scope": "native queue replacement source with mock guest event; "
                                     "no real guest HIPC or FC27 frame progress",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_native_queue_replacement_guest_wake_host"],
                                         sort_keys=True), flush=True)

                if ok and script == "check-fc27-f05-native-acquire-drop-wake-host.py":
                    acquired = re.findall(
                        r"F05_NATIVE_ACQUIRE_DROP_GUEST_WAKE_PASS frames=(\d+) stale_drops=(\d+) "
                        r"guest_event=(\d+) callbacks_unlocked=(\d+) normal_acquire_quiet=(\d+) "
                        r"present_later_quiet=(\d+) invalid_quiet=(\d+) "
                        r"untracked_release_quiet=(\d+) scope=source_extracted_mock_kernel",
                        result.stdout,
                    )
                    exclusions = (
                        "F05_REAL_GUEST_IPC_SCHEDULER_AND_FC27_PROGRESS_NOT_PROVEN"
                        in result.stdout
                    )
                    if acquired != [("260", "520", "260", "1", "1", "1", "1", "1")]*2 or not exclusions:
                        ok, reason = False, "f05_acquire_drop_guest_wake_witness_missing"
                    else:
                        fixture_metrics["F05_native_acquire_drop_wake_host"] = {
                            "frame_cycles": 260,
                            "reclaimed_queued_frames": 520,
                            "guest_events": 260,
                            "no_duplicate_on_normal_acquire": True,
                            "no_untracked_release_wake": True,
                            "callback_unlocked": True,
                            "compile_modes": ["O0", "O2"],
                            "scope": "native consumer acquisition and producer release listener "
                                     "on host mocks; no real guest HIPC scheduling or FC27 proof",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_native_acquire_drop_wake_host"],
                                         sort_keys=True), flush=True)

                if ok and script == "check-fc27-f05-native-consumer-disconnect-host.py":
                    terminals = re.findall(
                        r"F05_NATIVE_CONSUMER_DISCONNECT_WAKE_PASS host_waiters=(\d+) "
                        r"guest_event=(\d+) callback_unlocked=(\d+) quiet_error=(\d+) "
                        r"safe_stop=(\d+) scope=mock_kernel",
                        result.stdout,
                    )
                    excludes = "F05_REAL_GUEST_HIPC_FC27_LIVENESS_NOT_PROVEN" in result.stdout
                    if terminals != [("2", "1", "1", "1", "1")]*2 or not excludes:
                        ok, reason = False, "f05_consumer_terminal_wake_source_proof_missing"
                    else:
                        fixture_metrics["F05_consumer_terminal_guest_wake_host"] = {
                            "host_waiters": 2,
                            "guest_event_count": 1,
                            "callback_outside_lock": True,
                            "quiet_error": True,
                            "safe_stop": True,
                            "compile_modes": ["O0", "O2"],
                            "scope": "source-extracted consumer disconnect + producer listener; "
                                     "mock kernel event, guest HIPC unproven",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_consumer_terminal_guest_wake_host"],
                                         sort_keys=True), flush=True)

                if ok and script == "check-fc27-f05-producer-release-wake-host.py":
                    proofs = re.findall(
                        r"F05_PRODUCER_RELEASE_WAKE_HOST_PASS initial=(\d+) "
                        r"forwarded=(\d+) stop_before_close=(\d+) "
                        r"concurrent_release=(\d+) "
                        r"scope=source_extracted_listener_mock_guest_kernel_event",
                        result.stdout,
                    )
                    outstanding = (
                        "F05_GUEST_IPC_SCHEDULING_AND_REAL_GAME_PROGRESS_NOT_PROVEN"
                        in result.stdout
                    )
                    if proofs != [("260", "260", "1", "1")]*2 or not outstanding:
                        ok, reason = False, "f05_guest_release_wakeup_source_proof_missing"
                    else:
                        fixture_metrics["F05_guest_release_wake_host"] = {
                            "initial_release_callbacks": 260,
                            "delegate_callbacks": 260,
                            "concurrent_teardown": True,
                            "compile_modes": ["O0", "O2"],
                            "scope": "native producer listener with mock kernel event; "
                                     "actual guest wait, HIPC and FC27 liveness unproven",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F05_guest_release_wake_host"],
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
                if ok and script == "check-fc27-f05-native-nvdisp-vulkan-present-chain-host.py":
                    records = re.findall(
                        r"F05_NATIVE_NVDISP_VULKAN_PRESENT_CHAIN_PASS "
                        r"requests=(\d+) copies=(\d+) async_frame_pool=(\d+) "
                        r"fence_gated=(\d+) frame_order_preserved=(\d+) "
                        r"scope=source_extracted_host_mock_wsi_and_gpu",
                        result.stdout,
                    )
                    independent = re.findall(
                        r"F05_NV_DISP_GPU_SYNCPOINT_SOURCE_PASS requests=(\d+) "
                        r"delayed_and_immediate_fences=verified",
                        result.stdout,
                    )
                    binder_records = re.findall(
                        r"F05_NATIVE_IPC_BINDER_DISPATCH_PASS "
                        r"auto_transactions=(\d+) forwarded=(\d+) invalid_binders=(\d+) "
                        r"scope=source_extracted_host_mock_guest_parcels",
                        result.stdout,
                    )
                    queued = re.findall(
                        r"F05_NATIVE_BUFFERQUEUE_TO_VULKAN_CHAIN_PASS "
                        r"queued=(\d+) acquired_game=(\d+) acquired_hud=(\d+) "
                        r"composite=(\d+) callback_frames=(\d+) "
                        r"scope=source_extracted_host_mock_binder_and_wsi",
                        result.stdout,
                    )
                    bounded = result.stdout.count(
                        "F05_HID_IPC_AND_REAL_VULKAN_GPU_PRESENT_NOT_PROVEN"
                    ) == 1
                    if (records != [("260","260","7","1","1")]*2 or
                            independent != ["260","260"] or
                            queued != [("260",)*5]*2 or
                            binder_records != [("260","260","1")]*2 or not bounded):
                        ok,reason=False,"f05_linked_native_guest_to_present_missing"
                    else:
                        fixture_metrics["F05_linked_nvdisp_host1x_vulkan_present_host"] = {
                            "native_nvdisp_guest_requests": 260,
                            "native_nvnflinger_queue_buffers": 260,
                            "native_hos_binder_auto_transactions": 260,
                            "native_nvnflinger_acquisitions_per_layer": 260,
                            "native_hardware_compositions": 260,
                            "async_mock_present_copies": 260,
                            "frame_pool": 7,
                            "fence_gated_order": "verified",
                            "compile_modes": ["O0","O2"],
                            "scope": "three linked translation units executing selected "
                                     "nvdisp/GPU/Host1x, native BufferQueue "
                                     "producer/consumer/HardwareComposer, and "
                                     "RendererVulkan/PresentManager C++ with "
                                     "mock guest Binder, GPU and WSI. "
                                     "NOT HID/IPC or guest runtime progress.",
                        }
                        print("F05_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics[
                                  "F05_linked_nvdisp_host1x_vulkan_present_host"
                              ],sort_keys=True),flush=True)
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
                        r"claimed=1 pending_cancelled=1 independent=1 same_id_serial=1 stress=256",
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
                if ok and script == "check-fc27-f06-native-npad-lifo-host.py":
                    published = re.findall(
                        r"F06_NATIVE_NPAD_LIFO_HOST_PASS writes=(\d+) "
                        r"fullkey_order=(\d+) system_ext=(\d+) plus_release=(\d+) "
                        r"gated=(\d+) reconnect=(\d+) joycon_style=(\d+) "
                        r"scope=source_extracted_guest_lifo_mock_shared_memory",
                        result.stdout,
                    )
                    unproven = "F06_REAL_HIPC_AND_FC27_MATCH_TRANSITIONS_NOT_PROVEN" in result.stdout
                    if published != [("4","1","1","1","1","1","1")]*2 or not unproven:
                        ok, reason = False, "f06_guest_lifo_source_replay_missing"
                    else:
                        fixture_metrics["F06_guest_lifo_publication_host"] = {
                            "fullkey_writes": 4,
                            "monotonic_sample_numbers": True,
                            "guest_system_ext_copy": True,
                            "release_and_gates": True,
                            "reconnection": True,
                            "compile_modes": ["O0","O2"],
                            "scope": "native OnUpdate source writing mock guest LIFO; "
                                     "real HIPC game reads and transitions unproven",
                        }
                        print("F06_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F06_guest_lifo_publication_host"],
                                         sort_keys=True), flush=True)

                if ok and script == "check-fc27-f06-native-npad-handoff-host.py":
                    handoff = re.findall(
                        r"F06_NATIVE_NPAD_HANDOFF_PASS plus=(\d+) releases=(\d+) masks=(\d+) "
                        r"config_filter=(\d+) disconnect=(\d+) reconnect=(\d+) "
                        r"joycon_right=(\d+) "
                        r"scope=source_extracted_mock_controller_no_guest_lifo",
                        result.stdout,
                    )
                    excluded = (
                        "F06_GUEST_LIFO_GAME_ACTIONS_AND_FC27_PHASE_PROGRESS_NOT_PROVEN"
                        in result.stdout
                    )
                    if handoff != [("1",)*7]*2 or not excluded:
                        ok, reason = False, "f06_native_npad_handoff_witness_missing"
                    else:
                        fixture_metrics["F06_native_npad_handoff_host"] = {
                            "plus_to_npad_state": True,
                            "release_unchanged": True,
                            "filtered_and_disconnected": True,
                            "reconnect_and_joycon_style": True,
                            "compile_modes": ["O0", "O2"],
                            "scope": "native GetNpadButtons and RequestPadStateUpdate "
                                     "with mock controller. Guest LIFO/FC27 NOT proven",
                        }
                        print("F06_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F06_native_npad_handoff_host"],
                                         sort_keys=True), flush=True)

                if ok and script == "check-fc27-f06-native-pad-transition-host.py":
                    transitions = re.findall(
                        r"F06_NATIVE_PAD_TRANSITIONS_PASS "
                        r"phases=(\d+) action_edges=(\d+) options_plus_edges=(\d+) "
                        r"disconnect_releases=(\d+) home_chords=(\d+) "
                        r"menu_shortcuts=(\d+) touch_taps=(\d+) "
                        r"scope=source_extracted_host_mock_virtual_input_no_guest_Npad",
                        result.stdout)
                    missing_guest = (
                        "F06_REAL_GUEST_NPAD_GAMEPLAY_MAPPING_AND_MATCH_PROGRESS_NOT_PROVEN"
                        in result.stdout)
                    if transitions != [("5","5","5","1","1","1","1")]*2 or not missing_guest:
                        ok,reason=False,"f06_native_input_transition_witness_missing"
                    else:
                        fixture_metrics["F06_native_pad_transitions_host"] = {
                            "phases": 5,
                            "guest_action_edges": 5,
                            "guest_plus_edges": 5,
                            "disconnect_releases": 1,
                            "home_chords": 1,
                            "menu_shortcuts": 1,
                            "touch_taps": 1,
                            "compile_modes": ["O0","O2"],
                            "scope": "actual PS5 Pad::Consume and PadEngine::SetButtonState "
                                     "with native DualSense ABI but mock virtual HID sink. "
                                     "Game Npad consumption and FC27 phases not proven.",
                        }
                        print("F06_MEASURED_HOST_SUBPATH=" +
                              json.dumps(fixture_metrics["F06_native_pad_transitions_host"],
                                         sort_keys=True),flush=True)
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
    # F01 is the first PRE-CONSOLE technical exit with its full source
    # A/B criterion: native selection, guarded allocation, equivalent sampler
    # results, same-draw critical-section timing under a competing mutex.
    # This does not certify any game-level improvement, which requires PS5.
    f01_technical_exit = (
        all(item["ok"] for item in status["F01-cache-contention"]) and
        "F01_payload_allocation_host_mock" in fixture_metrics and
        "F01_sampler_lookup_host_mock" in fixture_metrics and
        "F01_native_lock_budget_host" in fixture_metrics
    )
    # F02: source-extracted pinned/current A32+A64 code must independently
    # prove cold/hot/partial/full cache behavior, cross-core isolation, and
    # before/after lock ownership. These are HOST technical proofs only:
    # guest translation cost and real PS5 performance remain unmeasured.
    f02_technical_exit = (
        all(item["ok"] for item in status["F02-jit-invalidation"]) and
        "F02_native_invalidation_lock_host" in fixture_metrics and
        "F02_cold_repeat_source_host" in fixture_metrics
    )
    # F03: technical HOST exit requires both selected TIC->feedback and
    # 240 ordinary frames plus a recovered frame in ONE C++ replay, with
    # unique HUD revisions, pause, remap and transient resource disappearance. Real pixels/device scanout are
    # still outside the pre-console evidence and must not be certified.
    f03_technical_exit = (
        all(item["ok"] for item in status["F03-hud-freshness"]) and
        "F03_tic_descriptor_feedback_host" in fixture_metrics and
        "F03_texture_to_present_host" in fixture_metrics
    )
    # F04 technical PRE-CONSOLE exit requires ONE real-source C++ replay
    # connecting cache map loss -> DMA -> invalidation -> alias -> staging,
    # as well as standalone Vulkan barrier/copy ownership regression checks.
    # The GPU address translation after unmap and device execution are mocked
    # and explicitly belong to F07, not this host technical certificate.
    f04_technical_exit = (
        f03_technical_exit and
        all(item["ok"] for item in status["F04-texture-integrity"]) and
        "F04_native_remap_dma_upload_host" in fixture_metrics
    )
    preconsole_exits = {
        "F01-cache-contention": bool(f01_technical_exit),
        "F02-jit-invalidation": bool(f02_technical_exit),
        "F03-hud-freshness": bool(f03_technical_exit),
        "F04-texture-integrity": bool(f04_technical_exit),
        "F05-guest-progress": False,
        "F06-input-and-pause": False,
    }
    remaining_exit_evidence = dict(UNPROVEN_EXIT_EVIDENCE)
    if f01_technical_exit:
        remaining_exit_evidence.pop("F01-cache-contention")
    if f02_technical_exit:
        remaining_exit_evidence.pop("F02-jit-invalidation")
    if f03_technical_exit:
        remaining_exit_evidence.pop("F03-hud-freshness")
    if f04_technical_exit:
        remaining_exit_evidence.pop("F04-texture-integrity")
    summary = {"scope": "PRECONSOLE_HOST_TECHNICAL_NOT_GAMEPLAY",
               "f01_to_f06_closed": sum(preconsole_exits.values()),
               "preconsole_exit_status": preconsole_exits,
               "console_qualified": False, "gameplay_qualified": False,
               "host_subpaths_passed": sum(c["ok"] for cs in status.values() for c in cs),
               "host_subpaths_total": sum(len(cs) for cs in status.values()),
               "fixture_metrics": fixture_metrics,
               "unproven_exit_evidence": remaining_exit_evidence,
               "gates": status}
    print("FC27_SIX_GATES_HOST_CHECKPOINT=" +
          json.dumps(summary, ensure_ascii=True, separators=(",", ":")), flush=True)
    table = ["## FC27 F01-F06 — host checkpoint (NOT gameplay qualification)",
             "| Criterion | Source-derived witnesses |", "| --- | --- |"]
    for gate, checks in status.items():
        label = "PASS" if all(x["ok"] for x in checks) else "FAIL"
        table.append(f"| {gate} | {label} ({sum(x['ok'] for x in checks)}/{len(checks)}) |")
    table += ["", f"{sum(preconsole_exits.values())}/6 PRE-CONSOLE technical "
                    "exits verified on host (each requires native-source metrics); "
                    "this is NOT console or FC27 in-game certification.",
              "", "#### Critical unproven exit evidence"]
    for gate, missing in remaining_exit_evidence.items():
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
