#!/usr/bin/env python3
"""R393 FC27 IPC forensic summary from existing five-second detailed logs.

Cumulative time measures completed IPC calls, NOT currently blocked calls.
No single IPC counter proves a deadlock or causality with stutter.
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

KV = re.compile(r"([a-zA-Z_][a-zA-Z_0-9]*)=(\d+(?:\.\d+)?)")


def fields(line: str) -> dict[str, float]:
    return {k: float(v) for k, v in KV.findall(line)}


def analyze(text: str) -> dict:
    frame = None
    windows: dict[int, dict] = {}
    previous: dict[int, tuple[int, int]] = {}
    prev_hist: dict[str, int] = {}
    for line in text.splitlines():
        if line.startswith("EDEN_VULKAN_FRAME "):
            data = fields(line)
            if "total" in data:
                frame = int(data["total"])
                windows.setdefault(frame, {"late50": int(data.get("late50", 0)),
                                          "threads": {}, "hist": {}})
        elif line.startswith("EDEN_DEV_IPC_THREAD ") and frame is not None:
            data = fields(line)
            if not {"tid", "calls", "ns", "max_ns"} <= data.keys():
                continue
            tid = int(data["tid"])
            calls, ns = int(data["calls"]), int(data["ns"])
            # Only positive monotonic deltas on the SAME thread ID.
            old = previous.get(tid)
            delta = None if old is None or calls < old[0] or ns < old[1] else (
                calls - old[0], ns - old[1])
            windows[frame]["threads"][tid] = {
                "calls": calls, "ns": ns,
                "max_ms": round(data["max_ns"] / 1e6, 3),
                "delta_calls": delta[0] if delta else None,
                "delta_ms": round(delta[1] / 1e6, 3) if delta else None,
            }
            previous[tid] = (calls, ns)
        elif line.startswith("EDEN_DEV_IPCHIST ") and frame is not None:
            data = fields(line)
            current = {k: int(v) for k, v in data.items()}
            windows[frame]["hist"] = {
                k: (v - prev_hist[k] if k in prev_hist and v >= prev_hist[k] else None)
                for k, v in current.items()
            }
            prev_hist = current
    # Entries represent only the top 12 cumulative threads per snapshot.
    # Missing threads cannot be assumed idle; avoid counting absent rows as zero.
    by_thread = defaultdict(lambda: {"measured_delta_ms": 0., "measured_calls": 0,
                                     "observed_windows": 0, "late50_in_windows": 0})
    for window in windows.values():
        for tid, row in window["threads"].items():
            if row["delta_ms"] is None:
                continue
            dest = by_thread[tid]
            dest["measured_delta_ms"] += row["delta_ms"]
            dest["measured_calls"] += row["delta_calls"]
            dest["observed_windows"] += 1
            dest["late50_in_windows"] += window["late50"]
    return {"windows": len(windows),
            "late50_total": sum(v["late50"] for v in windows.values()),
            "threads": dict(sorted(by_thread.items(),
                key=lambda x: x[1]["measured_delta_ms"], reverse=True)),
            "snapshots": windows}


def self_test() -> None:
    s = "\n".join([
        "EDEN_VULKAN_FRAME total=100 late50=4",
        "EDEN_DEV_IPC_THREAD tid=10 calls=5 ns=10000000 max_ns=5000000",
        "EDEN_DEV_IPCHIST lt50us=1 ge5ms=4 overflow_calls=0",
        "EDEN_VULKAN_FRAME total=200 late50=0",
        "EDEN_DEV_IPC_THREAD tid=10 calls=8 ns=16000000 max_ns=5000000",
        "EDEN_DEV_IPC_THREAD tid=11 calls=1 ns=3000000 max_ns=3000000",
        "EDEN_DEV_IPCHIST lt50us=2 ge5ms=5 overflow_calls=0",
        "EDEN_VULKAN_FRAME total=300 late50=8",
        "EDEN_DEV_IPC_THREAD tid=10 calls=12 ns=30000000 max_ns=6000000",
        "EDEN_DEV_IPCHIST lt50us=3 ge5ms=7 overflow_calls=0",
    ])
    d = analyze(s)
    assert d["windows"] == 3 and d["late50_total"] == 12
    assert d["threads"][10]["measured_delta_ms"] == 20
    assert d["threads"][10]["measured_calls"] == 7
    assert d["threads"][10]["late50_in_windows"] == 8
    assert d["snapshots"][100]["threads"][10]["delta_ms"] is None
    assert d["snapshots"][200]["hist"]["ge5ms"] == 1
    assert d["snapshots"][300]["hist"]["ge5ms"] == 2
    reset = analyze(s + "\nEDEN_VULKAN_FRAME total=400 late50=1"
                    "\nEDEN_DEV_IPC_THREAD tid=10 calls=1 ns=2000000 max_ns=2000000")
    assert reset["snapshots"][400]["threads"][10]["delta_ms"] is None
    print("PASS R393 IPC cumulative delta, histogram, reset and sampled top-12 semantics")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("log", nargs="?")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test()
        return
    if not a.log:
        p.error("provide log path or --self-test")
    result = analyze(Path(a.log).read_text(errors="replace"))
    print(f"Windows: {result['windows']}; late50: {result['late50_total']}")
    if not result["threads"]:
        print("No consecutive R393 detailed IPC thread snapshots found.")
    for tid, row in result["threads"].items():
        print(f"tid={tid} measured_delta_ms={row['measured_delta_ms']:.3f}"
              f" completed_calls={row['measured_calls']}"
              f" windows={row['observed_windows']}"
              f" late50_in_same_windows={row['late50_in_windows']}")
    print("Caution: only top-12 cumulative completed IPC waits are observable;"
          " no deadlock or stutter causality can be inferred from these alone.")


if __name__ == "__main__":
    main()
