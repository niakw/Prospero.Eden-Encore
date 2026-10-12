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


def analyze(log: str) -> dict:
    frames: dict[int, dict] = {}
    pressure: dict[int, dict] = {}
    gpu: dict[int, dict] = {}
    phases: dict[str, dict[int, dict]] = defaultdict(dict)
    for line in log.splitlines():
        if line.startswith("EDEN_VULKAN_FRAME "):
            value = values(line)
            if "total" in value:
                frames[int(value["total"])] = value
        elif line.startswith("EDEN_FRAME_PRESSURE "):
            value = values(line)
            if "frame" in value:
                pressure[int(value["frame"])] = value
        elif line.startswith("EDEN_DEV_GPU "):
            value = values(line)
            if "frame" in value:
                gpu[int(value["frame"])] = value
        elif line.startswith("EDEN_GPU_CACHE_PHASE "):
            match = PHASE.search(line)
            value = values(line)
            if match and "frame" in value:
                phases[match.group(1)][int(value["frame"])] = value
    keys = sorted(frames.keys() & pressure.keys() & gpu.keys())
    if not keys:
        raise ValueError("No matching EDEN_VULKAN_FRAME / EDEN_FRAME_PRESSURE / EDEN_DEV_GPU windows")
    rows = []
    preceding: dict[str, dict] = {}
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
            if before and snapshot.get("total_ns", 0) >= before.get("total_ns", 0):
                row["phase_ms:" + phase] = (snapshot["total_ns"] - before["total_ns"]) / 1e6
            preceding["phase:" + phase] = snapshot
        preceding["gpu"] = owner
        rows.append(row)
    full = [row for row in rows if row.get("gpu_full_ms", 0) > 0.001]
    stall = sum(row.get("late50", 0) for row in rows)
    in_full = sum(row.get("late50", 0) for row in full)
    return {
        "windows": len(rows),
        "late50_total": int(stall),
        "queue_full_windows": len(full),
        "late50_during_full": int(in_full),
        "late50_full_window_share": in_full / stall if stall else 0.0,
        "queue_wait_seconds": sum(row.get("gpu_full_ms", 0) for row in rows) / 1000,
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
            phase: {"sampled_ms": round(sum(row.get("phase_ms:" + phase, 0) for row in rows), 2),
                    "late50_correlation": round(correlation(rows, "phase_ms:" + phase, "late50"), 3)}
            for phase in sorted(phases)
        },
        "rows": rows,
    }


def self_test() -> None:
    sample = "\n".join([
        "EDEN_VULKAN_FRAME total=150 frames=150 seconds=5 fps=30 worst_ms=70 late50=4",
        "EDEN_FRAME_PRESSURE frame=150 gpu_full_ms=20 gpu_idle_ms=3500 gpu_dispatch_ms=1200",
        "EDEN_DEV_GPU frame=150 dispatch_calls=500 full_calls=10 full_ns=20000000 draws=100",
        "EDEN_GPU_CACHE_PHASE frame=150 phase=pair_wait total_ns=1000000",
        "EDEN_VULKAN_FRAME total=300 frames=150 seconds=5 fps=30 worst_ms=35 late50=0",
        "EDEN_FRAME_PRESSURE frame=300 gpu_full_ms=0 gpu_idle_ms=3800 gpu_dispatch_ms=1050",
        "EDEN_DEV_GPU frame=300 dispatch_calls=900 full_calls=10 full_ns=20000000 draws=280",
        "EDEN_GPU_CACHE_PHASE frame=300 phase=pair_wait total_ns=1400000",
    ])
    result = analyze(sample)
    assert result["windows"] == 2
    assert result["late50_total"] == 4
    assert result["queue_full_windows"] == 1
    assert result["late50_full_window_share"] == 1
    assert result["queue_wait_seconds"] == 0.02
    assert result["rows"][1]["delta_dispatch_calls"] == 400
    assert abs(result["cache_phases"]["pair_wait"]["sampled_ms"] - .4) < 1e-9
    print("FC27_TRACE_ANALYZER_SELF_TEST_PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.log:
        parser.error("Provide an actual PS5 heap log or --self-test")
    report = analyze(args.log.read_text(errors="replace"))
    print("FC27_TRACE windows={windows} late50={late50_total} queue_full_windows={queue_full_windows} "
          "late_in_full={late50_during_full} fraction={late50_full_window_share:.3f} "
          "queue_wait_seconds={queue_wait_seconds:.3f} gpu_thread_idle_fraction={gpu_thread_idle_fraction:.3f} "
          "mean_fps={mean_fps:.2f} worst_frame_ms={max_frame_ms:.1f}".format(**report))
    print("CORRELATIONS", report["late50_correlation"])
    for name, value in sorted(report["cache_phases"].items(),
                              key=lambda item: -item[1]["sampled_ms"]):
        print("CACHE_PHASE", name, value)
    print("NOTE: These are five-second window associations, not per-frame causation. "
          "GPU worker idle is not physical GPU utilization. "
          "Do not conflate gameplay stutter with frozen-but-presenting menus.")


if __name__ == "__main__":
    main()
