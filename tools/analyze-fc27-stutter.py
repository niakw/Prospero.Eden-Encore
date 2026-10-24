#!/usr/bin/env python3
"""Analyze PS5 FC27 five-second renderer pressure windows without changing the emulator.

This is a forensic correlation tool, NOT a root-cause oracle.
Usage: python3 tools/analyze-fc27-stutter.py heap.prev.log
       python3 tools/analyze-fc27-stutter.py --self-test
Requires Python standard library only; ignores unrelated log lines.
"""
from __future__ import annotations

import argparse
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path

KEY_VALUE = re.compile(r"([A-Za-z][A-Za-z_0-9]*)=(-?[0-9]+(?:\.[0-9]+)?)")
PHASE = re.compile(r"\bphase=([A-Za-z_0-9]+)")
BUILD = re.compile(r"\bsource_sha=([^\s]+)")
VALID_SHA = re.compile(r"^[0-9a-f]{40}$")


def source_sha(line: str) -> str | None:
    match = BUILD.search(line)
    if match is None:
        return None
    sha = match.group(1)
    if sha != "unknown" and not VALID_SHA.fullmatch(sha):
        raise ValueError(f"Malformed Eden source_sha: {sha[:80]}")
    return sha


def values(line: str) -> dict[str, float]:
    return {name: float(value) for name, value in KEY_VALUE.findall(line)}


def correlation(rows: list[dict], x: str, y: str) -> float:
    pairs = [(row[x], row[y]) for row in rows if x in row and y in row]
    if len(pairs) < 3:
        return 0.0
    a, b = zip(*pairs)
    mean_a, mean_b = statistics.mean(a), statistics.mean(b)
    spread_a = sum((value - mean_a) ** 2 for value in a)
    spread_b = sum((value - mean_b) ** 2 for value in b)
    if spread_a == 0 or spread_b == 0:
        return 0.0
    return sum((u - mean_a) * (v - mean_b) for u, v in pairs) / math.sqrt(spread_a * spread_b)


def phase_sampling_mode(phase: str) -> str:
    # Never present sampled window_ns as full wall time or compare rates
    # across differently sampled event families.
    if phase.startswith("guest_write_"):
        return "guest_write_1_in_64"
    if phase in ("descriptor_ring_finish", "descriptor_ring_preflight"):
        return "descriptor_gpu_wait_event_exact"
    return "gpu_draw_1_in_16_nominal"


def phase_summary(rows: list[dict], phase: str) -> dict:
    elapsed_ms = sum(row.get("phase_ms:" + phase, 0) for row in rows)
    samples = int(sum(row.get("phase_samples:" + phase, 0) for row in rows))
    maxima = [row["phase_max_us:" + phase] for row in rows
              if "phase_max_us:" + phase in row]
    return {
        "sampling": phase_sampling_mode(phase),
        "samples": samples,
        "sampled_ms": round(elapsed_ms, 2),
        "worst_sample_us": round(max(maxima), 3) if maxima else None,
        "mean_us_per_sample": round(elapsed_ms * 1000 / samples, 3) if samples else None,
        "late50_correlation": round(correlation(rows, "phase_ms:" + phase, "late50"), 3),
    }


def f01_paired_lock_phases(rows: list[dict]) -> dict:
    """Compare overlapping sampled lock-hold and Configure time, same draws.

    Configure runs inside PrepareDraw's paired mutexes. Comparing samples
    across unmatched counts or event families invents a contribution ratio.
    These are 1-in-16 sampled GPU-owner intervals, NOT full guest-thread
    blocked time and never a controlled baseline/new-build comparison.
    """
    pairs = []
    for row in rows:
        held_ns = row.get("phase_ms:pair_held")
        configure_ns = row.get("phase_ms:pipeline_configure")
        held_samples = row.get("phase_samples:pair_held")
        configure_samples = row.get("phase_samples:pipeline_configure")
        if (held_ns is None or configure_ns is None or
                held_samples is None or configure_samples is None or
                held_samples <= 0 or held_samples != configure_samples or
                held_ns <= 0 or configure_ns < 0 or
                configure_ns > held_ns * 1.02):
            continue
        pairs.append(row)
    if not pairs:
        return {"status": "NOT_MEASURED", "matched_windows": 0,
                "reason": "No comparable positive 1-in-16 pair-held/Configure deltas"}
    held = sum(r["phase_ms:pair_held"] for r in pairs)
    configured = sum(r["phase_ms:pipeline_configure"] for r in pairs)
    samples = sum(r["phase_samples:pair_held"] for r in pairs)
    return {"status": "SAMPLED_PAIR", "matched_windows": len(pairs),
            "matched_draw_samples": samples,
            "pair_held_mean_us": round(held * 1000 / samples, 3),
            "pipeline_configure_mean_us": round(configured * 1000 / samples, 3),
            "configure_share_of_sampled_lock_time": round(configured / held, 4),
            "scope": "same sampled GPU draws; nested times not additive; "
                     "NOT guest-thread wait or FC27 before-after speedup"}


def jit_cache_deltas(log: str) -> dict[int, dict]:
    """Separate scope-tagged, cumulative JIT-cache snapshots per guest core.

    No frame field exists in EDEN_PERF_JIT_CACHE. Its two counters MUST NOT be
    merged with EDEN_VULKAN_FRAME windows or inferred to cause an individual
    presentation gap. Only increasing adjacent native snapshots yield deltas.
    """
    fields = re.compile(r"\b(mono_ns|core|flush_all|flush_ranges)=(\d+)(?=\s|$)")
    prior: dict[int, tuple[int, int, int]] = {}
    data: dict[int, dict] = {}
    for line in log.splitlines():
        if "EDEN_GAME_SESSION_BEGIN" in line:
            # Multiple titles can reuse one native application process.
            prior.clear()
        if not line.startswith("EDEN_PERF_JIT_CACHE "):
            continue
        if "scope=standard_a64_applied" not in line.split():
            continue
        raw = fields.findall(line)
        parsed = dict(raw)
        if len(raw) != 4 or len(parsed) != 4:
            continue
        mono, core, full, ranges = (int(parsed[key]) for key in
                                     ("mono_ns", "core", "flush_all", "flush_ranges"))
        if core not in range(4):
            continue
        s = data.setdefault(core, {
            "observed_snapshots": 0, "measured_intervals": 0,
            "full_clears": None, "range_batches": None,
            "counter_resets": 0, "scope": "standard_a64_applied_not_frame_paired",
        })
        previous = prior.get(core)
        if previous is not None and mono <= previous[0]:
            # Invalid, duplicate or out-of-order sample: do not rebaseline.
            continue
        s["observed_snapshots"] += 1
        if previous is not None:
            _, prev_full, prev_ranges = previous
            if full >= prev_full and ranges >= prev_ranges:
                s["measured_intervals"] += 1
                s["full_clears"] = (s["full_clears"] or 0) + full - prev_full
                s["range_batches"] = (s["range_batches"] or 0) + ranges - prev_ranges
            else:
                # A new title or a diagnostic reset. Never sum the negative delta.
                s["counter_resets"] += 1
        prior[core] = (mono, full, ranges)
    return data


def analyze(log: str) -> dict:
    frames: dict[int, dict] = {}
    pressure: dict[int, dict] = {}
    gpu: dict[int, dict] = {}
    guest: dict[int, dict] = {}
    preflights: dict[int, dict] = {}
    jit_cores: dict[int, dict[int, dict]] = defaultdict(dict)
    present_witnesses: dict[int, dict] = {}
    previous_report_frame = 0
    dma_sync: dict[int, dict] = {}
    puller_semaphore: dict[int, dict] = {}
    current_frame: int | None = None
    source_commits: set[str] = set()
    phases: dict[str, dict[int, dict]] = defaultdict(dict)
    domains: dict[str, dict[int, dict]] = defaultdict(dict)
    # HLE reports cumulative *service* timings. Command 3 is an outer Binder
    # transaction, not the inner buffer-queue transaction type; never label it
    # DequeueBuffer without separately accounting for the dequeue timer.
    hle_previous: dict[tuple[str, str], tuple[int, int]] = {}
    hle_deltas: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    hle_re = re.compile(r"\bservice=(\S+)\s+cmd=(\d+)\s+calls=(\d+)\s+ns=(\d+)")
    for line in log.splitlines():
        if line.startswith("EDEN_BUILD_SOURCE "):
            sha = source_sha(line)
            if sha is None:
                raise ValueError("EDEN_BUILD_SOURCE has no source_sha field")
            source_commits.add(sha)
            if len(source_commits) > 1:
                raise ValueError("Mixed PS5 build source commits in one heap log")
        if line.startswith("EDEN_DEV_HLE "):
            match = hle_re.search(line)
            if match:
                service, command, raw_calls, raw_ns = match.groups()
                key = (service, command)
                calls, nanos = int(raw_calls), int(raw_ns)
                previous = hle_previous.get(key)
                if previous and calls >= previous[0] and nanos >= previous[1]:
                    hle_deltas[key][0] += calls - previous[0]
                    hle_deltas[key][1] += nanos - previous[1]
                hle_previous[key] = (calls, nanos)
        if line.startswith("EDEN_VULKAN_FRAME "):
            value = values(line)
            if "total" in value:
                new_frame = int(value["total"])
                previous_report_frame = current_frame if current_frame is not None and new_frame > current_frame else 0
                current_frame = new_frame
                frames[current_frame] = value
        elif line.startswith("EDEN_FRAME_PRESSURE "):
            value = values(line)
            if "frame" in value:
                pressure[int(value["frame"])] = value
        elif line.startswith("EDEN_DEV_GPU "):
            value = values(line)
            if "frame" in value:
                gpu[int(value["frame"])] = value
        elif line.startswith("EDEN_SCHEDULER_PREFLIGHT "):
            snapshot = values(line)
            if "frame" in snapshot and "dispatched" in snapshot:
                preflights[int(snapshot["frame"])] = snapshot
        elif line.startswith("EDEN_GPU_DMA_SYNC "):
            value = values(line)
            if {"frame", "calls", "ns"} <= value.keys():
                dma_sync[int(value["frame"])] = value
        elif line.startswith("EDEN_GPU_PULLER_SEMAPHORE "):
            value = values(line)
            if {"frame", "calls", "ns", "active_ns"} <= value.keys():
                puller_semaphore[int(value["frame"])] = value
        elif line.startswith("EDEN_FRAME_JIT_CORE "):
            value = values(line)
            if ({"frame", "core", "compile_ns", "compile_calls", "evacuations"} <= value.keys()
                    and int(value["core"]) in range(4)):
                jit_cores[int(value["frame"])][int(value["core"])] = value
        elif line.startswith("EDEN_PRESENT_INTERVAL_WITNESS "):
            # A pair of *compositor callbacks* measured by the opt-in native
            # witness. It is not a guest frame, mutex ownership or GPU proof.
            # The native record is emitted after the matching 5-s report.
            value = values(line)
            required = {"frame", "interval_ms", "jit_ns", "jit_calls",
                        "jit0_ns", "jit1_ns", "jit2_ns", "evacuations",
                        "cache_wait_ns", "gpu_fence_ns", "gpu_dispatch_ns",
                        "guest_sync_ns"}
            if (current_frame is not None and
                    "scope=between_presents" in line.split() and
                    required <= value.keys() and
                    previous_report_frame < value["frame"] <= current_frame and
                    value["frame"].is_integer() and
                    value["interval_ms"] >= 100.0 and
                    all(math.isfinite(value[k]) and value[k] >= 0 for k in required)):
                witness = {
                    "report_frame": current_frame,
                    "present_frame": int(value["frame"]),
                    "interval_ms": value["interval_ms"],
                    "jit_ms": value["jit_ns"] / 1e6,
                    "jit_calls": int(value["jit_calls"]),
                    "jit_core_ms": {
                        core: value[f"jit{core}_ns"] / 1e6 for core in range(3)
                    },
                    "evacuations": int(value["evacuations"]),
                    "cache_wait_ms": value["cache_wait_ns"] / 1e6,
                    "gpu_fence_ms": value["gpu_fence_ns"] / 1e6,
                    "gpu_dispatch_ms": value["gpu_dispatch_ns"] / 1e6,
                    "guest_sync_ms": value["guest_sync_ns"] / 1e6,
                }
                previous = present_witnesses.get(current_frame)
                if previous is None or witness["interval_ms"] > previous["interval_ms"]:
                    present_witnesses[current_frame] = witness
        elif line.startswith("EDEN_DEV_GUEST "):
            # The original report omits frame=. It is emitted directly
            # after EDEN_DEV_GPU for the same renderer snapshot.
            # Only associate it if that current Vulkan frame already has
            # a matching pressure and GPU report, never infer time stamps.
            if current_frame is not None and current_frame in pressure and current_frame in gpu:
                guest[current_frame] = values(line)
        elif line.startswith("EDEN_GPU_CACHE_PHASE "):
            match = PHASE.search(line)
            value = values(line)
            if match and "frame" in value:
                phases[match.group(1)][int(value["frame"])] = value
        elif line.startswith("EDEN_GUEST_CACHE_DOMAIN "):
            match = re.search(r"\bdomain=(buffer|texture)\b", line)
            value = values(line)
            if match and "frame" in value:
                domains[match.group(1)][int(value["frame"])] = value
    keys = sorted(frames.keys() & pressure.keys() & gpu.keys())
    if not keys:
        raise ValueError("No matching EDEN_VULKAN_FRAME / EDEN_FRAME_PRESSURE / EDEN_DEV_GPU windows")
    rows = []
    preceding: dict[str, dict] = {}
    previous_guest: dict | None = None
    previous_preflights: dict | None = None
    for frame in keys:
        row = {**frames[frame], **pressure[frame]}
        row["frame"] = frame
        owner = gpu[frame]
        for key in ("dispatch_calls", "full_calls", "full_ns", "draws"):
            if key in owner and key in preceding.get("gpu", {}):
                row["delta_" + key] = owner[key] - preceding["gpu"][key]
        for phase, occurrences in phases.items():
            snapshot = occurrences.get(frame)
            if not snapshot:
                continue
            before = preceding.get("phase:" + phase)
            if "max_ns" in snapshot and snapshot["max_ns"] > 0:
                # Native recorder resets this maximum every five seconds.
                row["phase_max_us:" + phase] = snapshot["max_ns"] / 1000
            if before and snapshot.get("total_ns", 0) >= before.get("total_ns", 0):
                row["phase_ms:" + phase] = (snapshot["total_ns"] - before["total_ns"]) / 1e6
                if ("samples" in snapshot and "samples" in before and
                        snapshot["samples"] >= before["samples"]):
                    row["phase_samples:" + phase] = (
                        snapshot["samples"] - before["samples"])
            preceding["phase:" + phase] = snapshot
        preflight = preflights.get(frame)
        if preflight is not None:
            if (previous_preflights is not None and
                    preflight["dispatched"] >= previous_preflights["dispatched"]):
                row["preflight_dispatches"] = (
                    preflight["dispatched"] - previous_preflights["dispatched"])
            previous_preflights = preflight
        guest_snapshot = guest.get(frame)
        if guest_snapshot is not None:
            if previous_guest is not None:
                for metric in ("cpu_write_calls", "cpu_write_ns",
                               "cpu_read_calls", "cpu_read_ns"):
                    now = guest_snapshot.get(metric)
                    before = previous_guest.get(metric)
                    if now is not None and before is not None and now >= before:
                        row["guest_delta_" + metric] = now - before
            previous_guest = guest_snapshot
        for domain, occurrences in domains.items():
            snap = occurrences.get(frame)
            if snap is None:
                continue
            # Native R364 already emits a per-snapshot delta, unlike the
            # cumulative older cache phase formats. Never sum totals twice.
            row["domain_wait_ms:" + domain] = snap.get("window_wait_ns", 0) / 1e6
            row["domain_contended:" + domain] = snap.get("window_contended", 0)
            row["domain_blocked:" + domain] = snap.get("window_blocked", 0)
        if frame in present_witnesses:
            row["present_interval_witness"] = present_witnesses[frame]
        # Each core is already an exact 5s delta; NEVER delta it again.
        # Missing snapshots stay unknown, not zero; four workers can run
        # simultaneously and must never be mistaken for 20s of frame stall.
        if frame in jit_cores:
            row["jit_cores"] = {
                core: {"compile_ms": stats["compile_ns"] / 1e6,
                       "compile_calls": int(stats["compile_calls"]),
                       "evacuations": int(stats["evacuations"])}
                for core, stats in jit_cores[frame].items()
            }
            for core, metrics in row["jit_cores"].items():
                row[f"jit_core_ms:{core}"] = metrics["compile_ms"]
        # R405/R406: only adjacent detailed GPU reports provide a valid cumulative
        # delta. Missing and reset source readings are not measured zeros.
        dma = dma_sync.get(frame)
        if dma is not None:
            if "active_ns" in dma:
                row["dma_sync_active_ms"] = dma["active_ns"] / 1e6
            prev_dma = preceding.get("dma_sync")
            if (prev_dma is not None and dma["ns"] >= prev_dma["ns"]
                    and dma["calls"] >= prev_dma["calls"]):
                row["dma_sync_wait_ms"] = (dma["ns"] - prev_dma["ns"]) / 1e6
                row["dma_sync_wait_calls"] = int(dma["calls"] - prev_dma["calls"])
            preceding["dma_sync"] = dma
        else:
            preceding.pop("dma_sync", None)
        # Active age is an instant observation, not cumulative, so never
        # subtract or sum it as completed work. A wait spanning windows may
        # show zero new completed calls while remaining active throughout.
        sem = puller_semaphore.get(frame)
        if sem is not None:
            row["puller_sem_active_ms"] = sem["active_ns"] / 1e6
            prev_sem = preceding.get("puller_semaphore")
            if (prev_sem is not None and sem["ns"] >= prev_sem["ns"]
                    and sem["calls"] >= prev_sem["calls"]):
                row["puller_sem_completed_ms"] = (sem["ns"] - prev_sem["ns"]) / 1e6
                row["puller_sem_completed_calls"] = int(sem["calls"] - prev_sem["calls"])
            preceding["puller_semaphore"] = sem
        else:
            preceding.pop("puller_semaphore", None)
        preceding["gpu"] = owner
        rows.append(row)
    full = [row for row in rows if row.get("gpu_full_ms", 0) > 0.001]
    stall = sum(row.get("late50", 0) for row in rows)
    in_full = sum(row.get("late50", 0) for row in full)
    return {
        "source_commit": next(iter(source_commits), None),
        "windows": len(rows),
        "late50_total": int(stall),
        # None means older build did not emit this metric; zero means R384
        # really measured no pre-dispatches after its first snapshot.
        "scheduler_preflight_dispatches": (
            int(sum(row["preflight_dispatches"] for row in rows
                    if "preflight_dispatches" in row))
            if any("preflight_dispatches" in row for row in rows) else None
        ),
        "scheduler_preflight_late50_correlation": (
            round(correlation(rows, "preflight_dispatches", "late50"), 3)
            if sum("preflight_dispatches" in row for row in rows) >= 3 else None
        ),
        "present_interval_witnesses": [
            present_witnesses[f] for f in keys if f in present_witnesses
        ],
        "jit_cache_events": jit_cache_deltas(log),
        "jit_core_summary": {
            core: {
                "observed_windows": len(observed),
                "compile_ms": round(sum(r["jit_cores"][core]["compile_ms"]
                                        for r in observed), 3),
                "compile_calls": sum(r["jit_cores"][core]["compile_calls"]
                                     for r in observed),
                "evacuations": sum(r["jit_cores"][core]["evacuations"]
                                   for r in observed),
                "late50_correlation": (round(correlation(
                    observed, f"jit_core_ms:{core}", "late50"), 3)
                    if len(observed) >= 3 else None),
            }
            for core in range(4)
            if (observed := [r for r in rows if core in r.get("jit_cores", {})])
        },
        "gpu_dma_sync": ({
            "observed_windows": len(dma_observed),
            "measured_wait_ms": round(sum(r["dma_sync_wait_ms"] for r in dma_observed), 3),
            "wait_calls": sum(r["dma_sync_wait_calls"] for r in dma_observed),
            "worst_frame_correlation": (round(correlation(
                dma_observed, "dma_sync_wait_ms", "worst_ms"), 3)
                if len(dma_observed) >= 3 else None),
            "late50_correlation": (round(correlation(
                dma_observed, "dma_sync_wait_ms", "late50"), 3)
                if len(dma_observed) >= 3 else None),
        } if (dma_observed := [r for r in rows if "dma_sync_wait_ms" in r]) else None),
        "gpu_puller_semaphore": ({
            "observed_snapshots": len(sem_seen),
            "completed_windows": len(sem_completed),
            "completed_wait_ms": round(sum(r["puller_sem_completed_ms"]
                                           for r in sem_completed), 3),
            "completed_calls": sum(r["puller_sem_completed_calls"]
                                    for r in sem_completed),
            "max_inflight_ms": round(max(r["puller_sem_active_ms"]
                                           for r in sem_seen), 3),
            "windows_with_inflight_wait": sum(r["puller_sem_active_ms"] > 0
                                               for r in sem_seen),
        } if (sem_seen := [r for r in rows if "puller_sem_active_ms" in r])
        and (sem_completed := [r for r in rows if "puller_sem_completed_ms" in r]) is not None
        else None),
        "queue_full_windows": len(full),
        "late50_during_full": int(in_full),
        "late50_full_window_share": in_full / stall if stall else 0.0,
        "queue_wait_seconds": sum(row.get("gpu_full_ms", 0) for row in rows) / 1000,
        "guest_dequeue_seconds": sum(row.get("guest_dequeue_ms", 0) for row in rows) / 1000,
        "guest_ipc_seconds": sum(row.get("guest_ipc_ms", 0) for row in rows) / 1000,
        "binder_auto_transaction_calls": hle_deltas[("IHOSBinderDriver", "3")][0],
        "binder_auto_transaction_seconds": hle_deltas[("IHOSBinderDriver", "3")][1] / 1e9,
        "gpu_thread_idle_fraction": (
            sum(row.get("gpu_idle_ms", 0) for row in rows) /
            (sum(row.get("seconds", 5.0) for row in rows) * 1000)
        ),
        "mean_fps": statistics.mean(row["fps"] for row in rows if "fps" in row),
        "max_frame_ms": max(row.get("worst_ms", 0) for row in rows),
        "late50_correlation": {
            key: round(correlation(rows, key, "late50"), 3)
            for key in ("gpu_full_ms", "gpu_dispatch_ms", "gpu_idle_ms",
                        "guest_dequeue_ms", "guest_ipc_ms", "cache_wait_ms",
                        "jit_ms", "delta_dispatch_calls")
        },
        "f01_paired_lock_phases": f01_paired_lock_phases(rows),
        "cache_phases": {
            phase: phase_summary(rows, phase)
            for phase in sorted(phases)
        },
        "guest_cpu_write_groups": {
            name: {
                "windows": len(group),
                "calls_per_window": round(statistics.mean(
                    row["guest_delta_cpu_write_calls"] for row in group), 1),
                "ms_per_window": round(statistics.mean(
                    row["guest_delta_cpu_write_ns"] for row in group) / 1e6, 2),
                "cache_collisions_per_window": round(statistics.mean(
                    row["cache_contended"] for row in group), 1),
                "guest_blocking_ms_per_window": round(statistics.mean(
                    row["cache_wait_ms"] for row in group), 2),
            }
            for name, group in (
                ("near30", [row for row in rows if row.get("fps", 0) >= 29.9 and
                             "guest_delta_cpu_write_calls" in row and
                             "guest_delta_cpu_write_ns" in row and
                             "cache_contended" in row and "cache_wait_ms" in row]),
                ("slow_sub25", [row for row in rows if row.get("fps", 0) < 25 and
                                "guest_delta_cpu_write_calls" in row and
                                "guest_delta_cpu_write_ns" in row and
                                "cache_contended" in row and "cache_wait_ms" in row]),
            ) if group
        },
        "guest_cpu_write_late50_correlations": {
            metric: round(correlation(rows, metric, "late50"), 3)
            for metric in ("guest_delta_cpu_write_calls", "guest_delta_cpu_write_ns")
        },
        "guest_cache_domains": {
            domain: {
                "wait_ms": round(sum(row.get("domain_wait_ms:" + domain, 0) for row in rows), 3),
                "contended": int(sum(row.get("domain_contended:" + domain, 0) for row in rows)),
                "blocked": int(sum(row.get("domain_blocked:" + domain, 0) for row in rows)),
                "late50_correlation": round(
                    correlation(rows, "domain_wait_ms:" + domain, "late50"), 3)
            }
            for domain in sorted(domains)
        },
        "rows": rows,
    }


def self_test() -> None:
    sample = "\n".join([
        "EDEN_BUILD_SOURCE source_sha=0f1e2d3c4b5a6978877665544332211000aabbcc",
        "EDEN_VULKAN_FRAME total=150 frames=150 seconds=5 fps=30 worst_ms=70 late50=4",
        "EDEN_FRAME_PRESSURE frame=150 gpu_full_ms=20 gpu_idle_ms=3500 gpu_dispatch_ms=1200 jit_ms=5",
        "EDEN_FRAME_JIT_CORE frame=150 core=0 compile_ns=3000000 compile_calls=5 evacuations=1",
        "EDEN_FRAME_JIT_CORE frame=150 core=1 compile_ns=2000000 compile_calls=8 evacuations=0",
        "EDEN_PRESENT_INTERVAL_WITNESS frame=149 interval_ms=180.000 jit_ns=3000000 jit_calls=5 jit0_ns=1500000 jit1_ns=1500000 jit2_ns=0 evacuations=1 cache_wait_ns=2000000 gpu_fence_ns=500000 gpu_dispatch_ns=700000 guest_sync_ns=0 scope=between_presents",
        "EDEN_DEV_GPU frame=150 dispatch_calls=500 full_calls=10 full_ns=20000000 draws=100",
        "EDEN_SCHEDULER_PREFLIGHT frame=150 dispatched=3",
        "EDEN_GPU_DMA_SYNC frame=150 calls=1 ns=2500000 active_ns=3000000",
        "EDEN_GPU_PULLER_SEMAPHORE frame=150 calls=4 ns=500000 active_ns=5000000",
        "EDEN_DEV_GUEST cpu_write_calls=100 cpu_write_ns=10000000 cpu_read_calls=30 cpu_read_ns=3000000",
        "EDEN_GPU_CACHE_PHASE frame=150 phase=pair_wait samples=10 total_ns=1000000",
        "EDEN_GPU_CACHE_PHASE frame=150 phase=pair_held samples=10 total_ns=5000000",
        "EDEN_GPU_CACHE_PHASE frame=150 phase=pipeline_configure samples=10 total_ns=4300000",
        "EDEN_GPU_CACHE_PHASE frame=150 phase=guest_write_buffer_wait samples=3 total_ns=200000 max_ns=150000",
        "EDEN_VULKAN_FRAME total=300 frames=150 seconds=5 fps=30 worst_ms=35 late50=0",
        "EDEN_FRAME_PRESSURE frame=300 gpu_full_ms=0 gpu_idle_ms=3800 gpu_dispatch_ms=1050 jit_ms=7",
        "EDEN_FRAME_JIT_CORE frame=300 core=0 compile_ns=2000000 compile_calls=2 evacuations=0",
        "EDEN_FRAME_JIT_CORE frame=300 core=1 compile_ns=5000000 compile_calls=4 evacuations=1",
        "EDEN_PRESENT_INTERVAL_WITNESS frame=299 interval_ms=125.000 jit_ns=1000000 jit_calls=3 jit0_ns=0 jit1_ns=1000000 jit2_ns=0 evacuations=0 cache_wait_ns=0 gpu_fence_ns=7000000 gpu_dispatch_ns=100000 guest_sync_ns=0 scope=between_presents",
        "EDEN_DEV_GPU frame=300 dispatch_calls=900 full_calls=10 full_ns=20000000 draws=280",
        "EDEN_SCHEDULER_PREFLIGHT frame=300 dispatched=11",
        "EDEN_GPU_DMA_SYNC frame=300 calls=3 ns=13000000 active_ns=0",
        "EDEN_GPU_PULLER_SEMAPHORE frame=300 calls=6 ns=2300000 active_ns=0",
        "EDEN_DEV_GUEST cpu_write_calls=250 cpu_write_ns=40000000 cpu_read_calls=75 cpu_read_ns=9000000",
        "EDEN_GPU_CACHE_PHASE frame=300 phase=pair_wait samples=14 total_ns=1400000",
        "EDEN_GPU_CACHE_PHASE frame=300 phase=pair_held samples=14 total_ns=7000000",
        "EDEN_GPU_CACHE_PHASE frame=300 phase=pipeline_configure samples=14 total_ns=6200000",
        "EDEN_GPU_CACHE_PHASE frame=300 phase=guest_write_buffer_wait samples=7 total_ns=600000 max_ns=270000",
        "EDEN_GUEST_CACHE_DOMAIN frame=150 domain=buffer contended=8 blocked=5 wait_ns=10000000 window_contended=8 window_blocked=5 window_wait_ns=10000000",
        "EDEN_GUEST_CACHE_DOMAIN frame=150 domain=texture contended=4 blocked=4 wait_ns=2000000 window_contended=4 window_blocked=4 window_wait_ns=2000000",
        "EDEN_GUEST_CACHE_DOMAIN frame=300 domain=buffer contended=10 blocked=7 wait_ns=13000000 window_contended=2 window_blocked=2 window_wait_ns=3000000",
        "EDEN_GUEST_CACHE_DOMAIN frame=300 domain=texture contended=5 blocked=5 wait_ns=2500000 window_contended=1 window_blocked=1 window_wait_ns=500000",
        "EDEN_DEV_HLE service=IHOSBinderDriver cmd=3 calls=2 ns=20000000",
        "EDEN_DEV_HLE service=IHOSBinderDriver cmd=3 calls=5 ns=70000000",
    ])
    result = analyze(sample)
    assert result["windows"] == 2
    assert result["jit_cache_events"] == {}  # older telemetry must remain unknown
    cache_samples = "\n".join([
        "EDEN_PERF_JIT_CACHE mono_ns=100000 core=0 flush_all=2 flush_ranges=3 scope=standard_a64_applied",
        "EDEN_PERF_JIT_CACHE mono_ns=110000 core=1 flush_all=5 flush_ranges=10 scope=standard_a64_applied",
        "EDEN_PERF_JIT_CACHE mono_ns=130000 core=0 flush_all=4 flush_ranges=8 scope=standard_a64_applied",
        "EDEN_PERF_JIT_CACHE mono_ns=140000 core=0 flush_all=4 flush_ranges=8 scope=standard_a64_applied",
        "EDEN_PERF_JIT_CACHE mono_ns=135000 core=0 flush_all=500 flush_ranges=500 scope=standard_a64_applied",
        "EDEN_PERF_JIT_CACHE mono_ns=150000 core=0 flush_all=5 flush_ranges=11 scope=standard_a64_applied",
        "EDEN_PERF_JIT_CACHE mono_ns=151000 core=1 flush_all=0 flush_ranges=0 scope=standard_a64_applied",
        "EDEN_PERF_JIT_CACHE mono_ns=160000 core=1 flush_all=1 flush_ranges=2 scope=standard_a64_applied",
        "EDEN_GAME_SESSION_BEGIN title=another",
        "EDEN_PERF_JIT_CACHE mono_ns=170000 core=0 flush_all=1 flush_ranges=1 scope=standard_a64_applied",
        "EDEN_PERF_JIT_CACHE mono_ns=180000 core=0 flush_all=3 flush_ranges=2 scope=standard_a64_applied",
    ])
    cache = analyze(sample + "\n" + cache_samples)["jit_cache_events"]
    assert cache[0]["observed_snapshots"] == 6
    assert cache[0]["measured_intervals"] == 4
    assert cache[0]["full_clears"] == 5  # 2 + 1 + 2 after title boundary
    assert cache[0]["range_batches"] == 9  # 5 + 3 + 1
    assert cache[0]["counter_resets"] == 0
    assert cache[1]["observed_snapshots"] == 3
    assert cache[1]["measured_intervals"] == 1
    assert cache[1]["counter_resets"] == 1
    assert cache[1]["full_clears"] == 1 and cache[1]["range_batches"] == 2
    assert cache[0]["scope"] == "standard_a64_applied_not_frame_paired"
    assert jit_cache_deltas(cache_samples.replace("scope=standard_a64_applied",
                                                  "scope=unspecified")) == {}
    assert jit_cache_deltas("EDEN_PERF_JIT_CACHE mono_ns=2 core=8 flush_all=1 flush_ranges=2 scope=standard_a64_applied") == {}
    assert jit_cache_deltas("EDEN_PERF_JIT_CACHE mono_ns=2 core=0 flush_all=1 scope=standard_a64_applied") == {}

    expected_sha = "0f1e2d3c4b5a6978877665544332211000aabbcc"
    assert result["source_commit"] == expected_sha
    assert analyze(sample.replace("EDEN_BUILD_SOURCE", "NO_BUILD_SOURCE"))["source_commit"] is None
    assert source_sha("source_sha=unknown") == "unknown"
    assert source_sha("source_sha=" + expected_sha) == expected_sha
    for broken in ("source_sha=1234", "source_sha=UPPERCASE"):
        try:
            source_sha(broken)
        except ValueError:
            pass
        else:
            raise AssertionError("unverified Git source accepted: " + broken)
    try:
        analyze(sample.replace("EDEN_BUILD_SOURCE source_sha=" + expected_sha,
                               "EDEN_BUILD_SOURCE source_sha=aa" + expected_sha[2:] +
                               "\nEDEN_BUILD_SOURCE source_sha=" + expected_sha))
    except ValueError:
        pass
    else:
        raise AssertionError("mixed build SHAs were not rejected")
    assert result["late50_total"] == 4
    assert result["gpu_dma_sync"]["observed_windows"] == 1
    assert result["rows"][0]["dma_sync_active_ms"] == 3
    assert result["rows"][1]["dma_sync_active_ms"] == 0
    assert result["gpu_puller_semaphore"]["observed_snapshots"] == 2
    assert result["gpu_puller_semaphore"]["completed_windows"] == 1
    assert result["gpu_puller_semaphore"]["completed_wait_ms"] == 1.8
    assert result["gpu_puller_semaphore"]["completed_calls"] == 2
    assert result["gpu_puller_semaphore"]["max_inflight_ms"] == 5
    assert result["gpu_puller_semaphore"]["windows_with_inflight_wait"] == 1
    assert analyze(sample.replace("EDEN_GPU_PULLER_SEMAPHORE", "NO_PULLER_SEMAPHORE"))[
        "gpu_puller_semaphore"] is None
    assert result["gpu_dma_sync"]["measured_wait_ms"] == 10.5
    assert result["gpu_dma_sync"]["wait_calls"] == 2
    assert result["gpu_dma_sync"]["worst_frame_correlation"] is None
    assert analyze(sample.replace("EDEN_GPU_DMA_SYNC", "NO_DMA_SYNC"))["gpu_dma_sync"] is None
    witnesses = result["present_interval_witnesses"]
    assert len(witnesses) == 2
    assert witnesses[0]["report_frame"] == 150
    assert witnesses[0]["present_frame"] == 149
    assert witnesses[0]["jit_ms"] == 3.0
    assert witnesses[0]["jit_core_ms"][0] == 1.5
    assert witnesses[0]["cache_wait_ms"] == 2.0
    assert witnesses[1]["gpu_fence_ms"] == 7.0
    assert result["rows"][0]["present_interval_witness"] == witnesses[0]
    assert analyze(sample.replace("EDEN_PRESENT_INTERVAL_WITNESS", "OLD_WITNESS"))["present_interval_witnesses"] == []
    assert len(analyze(sample.replace("scope=between_presents", "scope=unverified"))["present_interval_witnesses"]) == 0
    assert len(analyze(sample.replace("frame=149 interval_ms=180.000", "frame=151 interval_ms=180.000"))["present_interval_witnesses"]) == 1
    assert len(analyze(sample.replace("interval_ms=125.000", "interval_ms=99.000"))["present_interval_witnesses"]) == 1
    assert result["jit_core_summary"][0]["compile_ms"] == 5
    assert result["jit_core_summary"][0]["compile_calls"] == 7
    assert result["jit_core_summary"][0]["evacuations"] == 1
    assert result["jit_core_summary"][0]["late50_correlation"] is None
    assert result["jit_core_summary"][1]["compile_ms"] == 7
    assert result["rows"][1]["jit_cores"][1]["compile_ms"] == 5
    assert analyze(sample.replace("EDEN_FRAME_JIT_CORE", "NO_JIT_CORE"))[
        "jit_core_summary"] == {}
    assert result["scheduler_preflight_dispatches"] == 8
    assert result["scheduler_preflight_late50_correlation"] is None
    assert analyze(sample.replace("EDEN_SCHEDULER_PREFLIGHT", "OMITTED_PREFLIGHT"))[
        "scheduler_preflight_dispatches"] is None
    assert result["queue_full_windows"] == 1
    assert result["late50_full_window_share"] == 1
    assert result["queue_wait_seconds"] == 0.02
    assert result["binder_auto_transaction_calls"] == 3
    assert result["binder_auto_transaction_seconds"] == 0.05
    assert result["rows"][1]["delta_dispatch_calls"] == 400
    assert result["rows"][1]["guest_delta_cpu_write_calls"] == 150
    assert result["rows"][1]["guest_delta_cpu_write_ns"] == 30000000
    assert result["rows"][1]["guest_delta_cpu_read_calls"] == 45
    assert abs(result["cache_phases"]["pair_wait"]["sampled_ms"] - .4) < 1e-9
    assert result["cache_phases"]["pair_wait"]["samples"] == 4
    assert result["cache_phases"]["pair_wait"]["sampling"] == "gpu_draw_1_in_16_nominal"
    assert result["cache_phases"]["pair_wait"]["mean_us_per_sample"] == 100
    f01 = result["f01_paired_lock_phases"]
    assert f01["status"] == "SAMPLED_PAIR" and f01["matched_windows"] == 1
    assert f01["matched_draw_samples"] == 4
    assert f01["pair_held_mean_us"] == 500.0
    assert f01["pipeline_configure_mean_us"] == 475.0
    assert f01["configure_share_of_sampled_lock_time"] == .95
    # Missing, mismatched and impossible nested phase samples never become
    # fabricated evidence of lock-time improvement or FPS changes.
    missing = analyze(sample.replace("phase=pipeline_configure", "phase=missing"))
    assert missing["f01_paired_lock_phases"]["status"] == "NOT_MEASURED"
    mismatch = analyze(sample.replace("phase=pipeline_configure samples=14",
                                      "phase=pipeline_configure samples=13"))
    assert mismatch["f01_paired_lock_phases"]["status"] == "NOT_MEASURED"
    impossible = analyze(sample.replace("pipeline_configure samples=14 total_ns=6200000",
                                        "pipeline_configure samples=14 total_ns=9000000"))
    assert impossible["f01_paired_lock_phases"]["status"] == "NOT_MEASURED"
    guest_phase = result["cache_phases"]["guest_write_buffer_wait"]
    assert guest_phase["samples"] == 4
    assert guest_phase["sampling"] == "guest_write_1_in_64"
    assert guest_phase["sampled_ms"] == .4
    assert guest_phase["mean_us_per_sample"] == 100
    assert guest_phase["worst_sample_us"] == 270
    assert phase_sampling_mode("descriptor_ring_finish") == "descriptor_gpu_wait_event_exact"
    assert phase_summary([{"phase_ms:guest_write_texture_wait": 5}], "guest_write_texture_wait")[
        "mean_us_per_sample"] is None
    assert result["guest_cache_domains"]["buffer"]["contended"] == 10
    assert result["guest_cache_domains"]["buffer"]["blocked"] == 7
    assert abs(result["guest_cache_domains"]["buffer"]["wait_ms"] - 13) < 1e-8
    assert result["guest_cache_domains"]["texture"]["contended"] == 5
    assert abs(result["guest_cache_domains"]["texture"]["wait_ms"] - 2.5) < 1e-8
    # Legacy files lacking *both* optional domain and guest snapshot fields
    # remain valid and do not invent new metrics.
    legacy = analyze(sample.replace("EDEN_GUEST_CACHE_DOMAIN", "IGNORED_DOMAIN")
                           .replace("EDEN_DEV_GUEST", "IGNORED_GUEST"))
    assert legacy["guest_cache_domains"] == {}
    assert legacy["guest_cpu_write_groups"] == {}
    assert legacy["guest_cpu_write_late50_correlations"] == {
        "guest_delta_cpu_write_calls": 0.0,
        "guest_delta_cpu_write_ns": 0.0,
    }
    print("FC27_TRACE_ANALYZER_SELF_TEST_PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--require-build-source", action="store_true",
                        help="reject legacy heap logs without an immutable 40-character Git commit")
    parser.add_argument("--boot-trace", type=Path,
                        help="corroborate source_sha against the same PS5 session's boot trace")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.log:
        parser.error("Provide an actual PS5 heap log or --self-test")
    report = analyze(args.log.read_text(errors="replace"))
    reported_sha = report["source_commit"]
    if args.require_build_source and (reported_sha is None or reported_sha == "unknown"):
        parser.error("UNVERIFIED_BUILD: this legacy log lacks a valid 40-hex EDEN_BUILD_SOURCE SHA")
    if args.boot_trace is not None:
        boot_sources = {source_sha(line)
                        for line in args.boot_trace.read_text(errors="replace").splitlines()
                        if "source_sha=" in line}
        if len(boot_sources) != 1 or reported_sha not in boot_sources:
            parser.error("BOOT_PROVENANCE_MISMATCH: missing or nonmatching boot/heap SHA")
    print("FC27_BUILD source_sha=" + (reported_sha or "unverified_pre_R368"))
    print("FC27_TRACE windows={windows} late50={late50_total} queue_full_windows={queue_full_windows} "
          "late_in_full={late50_during_full} fraction={late50_full_window_share:.3f} "
          "queue_wait_seconds={queue_wait_seconds:.3f} gpu_thread_idle_fraction={gpu_thread_idle_fraction:.3f} "
          "mean_fps={mean_fps:.2f} worst_frame_ms={max_frame_ms:.1f}".format(**report))
    print("GUEST_BUFFER_DEQUEUE seconds={guest_dequeue_seconds:.3f} "
          "guest_ipc_seconds={guest_ipc_seconds:.3f} "
          "binder_auto_calls={binder_auto_transaction_calls} "
          "binder_auto_seconds={binder_auto_transaction_seconds:.3f}".format(**report))
    print("CORRELATIONS", report["late50_correlation"])
    if report["gpu_dma_sync"] is not None:
        print("GPU_DMA_SYNC_WAIT", report["gpu_dma_sync"])
        print("NOTE: DMA sync wait is a subcomponent of Scheduler::Push,"
              " not physical GPU busy time or proof of stutter causality.")
    else:
        print("GPU_DMA_SYNC_WAIT unavailable (pre-R405 logs)")
    if report["gpu_puller_semaphore"] is not None:
        print("GPU_PULLER_SEMAPHORE", report["gpu_puller_semaphore"])
        print("NOTE: active_ns is a snapshot of an unfinished guest semaphore"
              " wait; do not add it to completed time or infer deadlock alone.")
    else:
        print("GPU_PULLER_SEMAPHORE unavailable (pre-R406 logs)")
    if report["present_interval_witnesses"]:
        print("PRESENT_INTERVAL_WITNESSES count=" + str(len(report["present_interval_witnesses"])))
        for witness in sorted(report["present_interval_witnesses"],
                              key=lambda entry: entry["interval_ms"], reverse=True)[:5]:
            print("PRESENT_INTERVAL_WITNESS", witness)
        print("NOTE: These are worker-counter deltas BETWEEN TWO PRESENTATIONS,"
              " not per-guest-frame timing, GPU ownership or a proven freeze cause.")
    else:
        print("PRESENT_INTERVAL_WITNESSES unavailable (no validated opt-in pair)")
    if report["jit_cache_events"]:
        print("JIT_CACHE_APPLIED_SNAPSHOT_DELTAS", report["jit_cache_events"])
        print("NOTE: Per-core JIT cache snapshots have no renderer frame ID;"
              " they are NOT attributable to individual presents or freezes.")
    else:
        print("JIT_CACHE_APPLIED_SNAPSHOT_DELTAS unavailable (no matching tagged native DEV logs)")
    if report["jit_core_summary"]:
        print("GUEST_JIT_CORE_INTERVALS", report["jit_core_summary"])
        print("NOTE: JIT per-core intervals are overlapping CPU work, not wall-clock"
              " compositor stalls; missing cores are unknown, not zero.")
    else:
        print("GUEST_JIT_CORE_INTERVALS unavailable (pre-R404 logs)")
    if report["guest_cpu_write_groups"]:
        print("GUEST_CPU_WRITE_GROUPS", report["guest_cpu_write_groups"])
        print("GUEST_CPU_WRITE_LATE50_CORRELATIONS",
              report["guest_cpu_write_late50_correlations"])
    else:
        print("GUEST_CPU_WRITE_GROUPS unavailable (no two successive paired guest samples)")
    print("F01_MATCHED_LOCK_CONFIGURE", report["f01_paired_lock_phases"])
    for name, value in sorted(report["cache_phases"].items(),
                              key=lambda item: (item[1]["sampling"], item[0])):
        print("CACHE_PHASE", name, value)
    print("NOTE: Cache phase durations are SAMPLES only (GPU draws generally 1/16; "
          "guest CPU writes 1/64; descriptor ring waits are exact events). "
          "Compare mean_us_per_sample within an event family, never raw "
          "sampled_ms between families or as full CPU/GPU wall time.")
    if report["guest_cache_domains"]:
        for name, value in report["guest_cache_domains"].items():
            print("GUEST_CACHE_DOMAIN", name, value)
    else:
        print("GUEST_CACHE_DOMAIN unavailable (pre-R364 console log; do not infer zero contention)")
    print("NOTE: Outer Binder command 3 multiplexes graphics transactions (including DequeueBuffer); "
          "its accumulated wall time is NOT proof of a single buffer queue deadlock.")
    print("NOTE: These are five-second window associations, not per-frame causation. "
          "GPU worker idle is not physical GPU utilization. "
          "Do not conflate gameplay stutter with frozen-but-presenting menus.")


if __name__ == "__main__":
    main()
