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


def analyze(log: str) -> dict:
    frames: dict[int, dict] = {}
    pressure: dict[int, dict] = {}
    gpu: dict[int, dict] = {}
    guest: dict[int, dict] = {}
    preflights: dict[int, dict] = {}
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
                current_frame = int(value["total"])
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
        "EDEN_FRAME_PRESSURE frame=150 gpu_full_ms=20 gpu_idle_ms=3500 gpu_dispatch_ms=1200",
        "EDEN_DEV_GPU frame=150 dispatch_calls=500 full_calls=10 full_ns=20000000 draws=100",
        "EDEN_SCHEDULER_PREFLIGHT frame=150 dispatched=3",
        "EDEN_DEV_GUEST cpu_write_calls=100 cpu_write_ns=10000000 cpu_read_calls=30 cpu_read_ns=3000000",
        "EDEN_GPU_CACHE_PHASE frame=150 phase=pair_wait samples=10 total_ns=1000000",
        "EDEN_GPU_CACHE_PHASE frame=150 phase=guest_write_buffer_wait samples=3 total_ns=200000 max_ns=150000",
        "EDEN_VULKAN_FRAME total=300 frames=150 seconds=5 fps=30 worst_ms=35 late50=0",
        "EDEN_FRAME_PRESSURE frame=300 gpu_full_ms=0 gpu_idle_ms=3800 gpu_dispatch_ms=1050",
        "EDEN_DEV_GPU frame=300 dispatch_calls=900 full_calls=10 full_ns=20000000 draws=280",
        "EDEN_SCHEDULER_PREFLIGHT frame=300 dispatched=11",
        "EDEN_DEV_GUEST cpu_write_calls=250 cpu_write_ns=40000000 cpu_read_calls=75 cpu_read_ns=9000000",
        "EDEN_GPU_CACHE_PHASE frame=300 phase=pair_wait samples=14 total_ns=1400000",
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
    if report["guest_cpu_write_groups"]:
        print("GUEST_CPU_WRITE_GROUPS", report["guest_cpu_write_groups"])
        print("GUEST_CPU_WRITE_LATE50_CORRELATIONS",
              report["guest_cpu_write_late50_correlations"])
    else:
        print("GUEST_CPU_WRITE_GROUPS unavailable (no two successive paired guest samples)")
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
