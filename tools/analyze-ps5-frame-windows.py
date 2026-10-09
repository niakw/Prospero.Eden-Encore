#!/usr/bin/env python3
"""Offline R236/R237/R238 PS5 frame + CPU/GPU/JIT/IPC/memory comparison.

Read existing heap.log snapshots; never modify source logs or the PS5.
IMPORTANT: matched time windows are not necessarily matched GAME SCENES.
This tool separates evidence from hypotheses. It does not measure the
hardware GPU's occupancy or a console-wide CPU utilization percentage.

Usage (only when the user authorizes executing tests):
  python3 tools/analyze-ps5-frame-windows.py heap-r236.log heap-r237.log
"""
from __future__ import annotations

import argparse
import dataclasses
import re
import statistics
from pathlib import Path

VALUE = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)=(-?[0-9]+(?:\.[0-9]+)?)")

def read_values(line: str) -> dict[str, float]:
    return {key: float(value) for key, value in VALUE.findall(line)}

@dataclasses.dataclass
class Trace:
    filename: Path
    frames: list[dict[str, float]]
    gpu: list[dict[str, float]]
    guest: list[dict[str, float]]
    cpu: dict[int, list[dict[str, float]]]
    jit: dict[int, list[dict[str, float]]]
    budget: list[dict[str, float]]
    sparse: list[dict[str, float]]
    memory_live: list[dict[str, float]]
    owner_clock_valid: bool
    cross_thread_clock_valid: bool

    @classmethod
    def load(cls, filename: Path) -> "Trace":
        lines = filename.read_text(encoding="utf-8", errors="replace").splitlines()
        frames: list[dict[str, float]] = []
        gpu: list[dict[str, float]] = []
        guest: list[dict[str, float]] = []
        cpu = {n: [] for n in range(4)}
        jit = {n: [] for n in range(4)}
        budget: list[dict[str, float]] = []
        sparse: list[dict[str, float]] = []
        memory_live: list[dict[str, float]] = []
        for line in lines:
            if line.startswith("EDEN_VULKAN_FRAME frames="):
                frames.append(read_values(line))
            elif line.startswith("EDEN_DEV_GPU frame="):
                gpu.append(read_values(line))
            elif line.startswith("EDEN_DEV_GUEST cpu_write_calls="):
                guest.append(read_values(line))
            elif line.startswith("EDEN_PERF_CPU_POINT core="):
                info = read_values(line)
                cpu[int(info["core"])].append(info)
            elif line.startswith("EDEN_PERF_PROGRESS mono_ns="):
                info = read_values(line)
                jit[int(info["core"])].append(info)
            elif line.startswith("EDEN_VULKAN_TEXTURE_BUDGET "):
                budget.append(read_values(line))
            elif line.startswith("EDEN_JIT_SPARSE_MEMORY phase=dev-profile"):
                sparse.append(read_values(line))
            elif line.startswith("EDEN_MEMORY_LIVE frame="):
                memory_live.append(read_values(line))
        return cls(
            filename, frames, gpu, guest, cpu, jit, budget, sparse, memory_live,
            any(line.startswith("EDEN_PERF_OWNER_CLOCK_CHECK valid=1 ") for line in lines),
            any(line.startswith("EDEN_PERF_CPU_CLOCK_CHECK valid=1 ") for line in lines),
        )

    def windows(self) -> int:
        return min(len(self.frames), len(self.gpu), len(self.guest),
                   *(len(self.cpu[k]) for k in range(3)),
                   *(len(self.jit[k]) for k in range(3)))

    def report_window(self, index: int) -> dict[str, float]:
        # These counters are cumulative; taking DELTAS is mandatory.
        f = self.frames[index]
        def delta(s: list[dict[str, float]], key: str) -> float:
            return s[index][key] - s[index-1][key]
        cpu = [max(0.0, delta(self.cpu[k], "cpu_ns") / 1e9)
               for k in range(3)]
        return {
            "fps": f["fps"], "worst_ms": f["worst_ms"],
            "late50": f.get("late50", 0),
            "late100": f.get("late100", 0),
            "late200": f.get("late200", 0),
            "jit_ms": sum(delta(self.jit[k], "compile_ns") for k in range(3))/1e6,
            "jit_blocks": sum(delta(self.jit[k], "compilations") for k in range(3)),
            "cpu_min_s": min(cpu), "cpu_max_s": max(cpu),
            "gpu_worker_cpu_ms": delta(self.gpu, "cpu_ns") / 1e6,
            "gpu_worker_wait_ms": delta(self.gpu, "idle_ns") / 1e6,
            "gpu_full_queue_ms": delta(self.gpu, "full_ns") / 1e6,
            "guest_ipc_ms": delta(self.guest, "ipc_ns") / 1e6,
            "guest_dequeue_ms": delta(self.guest, "dequeue_ns") / 1e6,
            "cache_blocked": delta(self.guest, "cache_lock_blocked"),
            "cache_contended": delta(self.guest, "cache_lock_contended"),
            # 0 can mean no successful kernel pressure probe yet; never
            # present an unqualified zero as measured free direct RAM.
            "direct_free_mib": (self.memory_live[index].get("largest_last_confirmed", 0)
                                / (1024**2) if index < len(self.memory_live)
                                and self.memory_live[index].get("largest_last_confirmed", 0) > 0 else -1),
            "direct_memory_short": (self.memory_live[index].get("short", -1)
                                    if index < len(self.memory_live) else -1),
        }

def print_trace(trace: Trace, prefix: int | None) -> None:
    limit = min(len(trace.frames), prefix) if prefix else len(trace.frames)
    if limit == 0:
        print(f"{trace.filename}: no rendered-frame data")
        return
    v = trace.frames[:limit]
    seconds = sum(f["seconds"] for f in v)
    print(f"TRACE {trace.filename} windows={limit} seconds={seconds:.1f}")
    print(f"  fps weighted={sum(f['frames'] for f in v)/seconds:.2f}"
          f" median={statistics.median(f['fps'] for f in v):.2f}"
          f" min_5s={min(f['fps'] for f in v):.2f}"
          f" below20={sum(f['fps'] < 20 for f in v)}")
    print("  intervals >50ms={} >100ms={} >200ms={} longest={:.0f}ms".format(
        *(int(sum(f.get(x, 0) for f in v)) for x in ("late50", "late100", "late200")),
        max(f["worst_ms"] for f in v)))
    if trace.budget:
        print("  Vulkan texture-cache bytes: peak={} expected={} critical={} memory_short={}".format(
            int(max(x.get("usage", 0) for x in trace.budget)),
            int(trace.budget[-1].get("expected", 0)),
            int(trace.budget[-1].get("critical", 0)),
            int(max(x.get("memory_short", 0) for x in trace.budget))))
    if trace.sparse:
        print("  sparse JIT: committed_peak_MiB={:.1f} virtual_reserved_MiB={:.1f}".format(
            max(x.get("committed", 0) for x in trace.sparse)/(1024**2),
            trace.sparse[-1].get("reserved", 0)/(1024**2)))
    confirmed = [x["largest_last_confirmed"] for x in trace.memory_live
                 if x.get("largest_last_confirmed", 0) > 0]
    if confirmed:
        print("  direct memory largest-free confirmed: min_MiB={:.1f} last_MiB={:.1f}".format(
            min(confirmed)/(1024**2), confirmed[-1]/(1024**2)))
    print(f"  owner_thread_cpu_clock_valid={trace.owner_clock_valid}"
          f" cross_thread_clock_valid={trace.cross_thread_clock_valid}")
    n = min(trace.windows(), limit)
    if n <= 1:
        return
    snapshots = [(i, trace.report_window(i)) for i in range(1, n)]
    slow = sorted(snapshots, key=lambda a: a[1]["fps"])[:8]
    fast = sorted(snapshots, key=lambda a: a[1]["fps"], reverse=True)[:8]
    for label, group in (("slowest", slow), ("fastest", fast)):
        print(f"  {label} windows (times represent per-window deltas, NOT whole-console load):")
        for i, w in group:
            print(
                f"    #{i} fps={w['fps']:.2f} worst_ms={w['worst_ms']:.0f}"
                f" jit_ms={w['jit_ms']:.0f} guest_CPU_s={w['cpu_min_s']:.2f}-{w['cpu_max_s']:.2f}"
                f" gpu_worker_cpu_ms={w['gpu_worker_cpu_ms']:.0f}"
                f" gpu_worker_wait_ms={w['gpu_worker_wait_ms']:.0f}"
                f" gpu_queue_full_ms={w['gpu_full_queue_ms']:.0f}"
                f" ipc_ms={w['guest_ipc_ms']:.0f}"
                f" cache_blocked={int(w['cache_blocked'])}"
                + (f" direct_free_MiB={w['direct_free_mib']:.1f}"
                   f" pressure_short={int(w['direct_memory_short'])}"
                   if w["direct_free_mib"] >= 0 else ""))
    print("  Interpretation: device GPU occupancy is unmeasured; full guest CPU"
          " threads alone do not prove why one scene falls from 30 to 12 FPS.")

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("logs", type=Path, nargs="+", help="Previously retrieved heap.log files")
    args = ap.parse_args()
    traces = [Trace.load(path) for path in args.logs]
    comparable = min(len(t.frames) for t in traces) if len(traces) > 1 else None
    for trace in traces:
        print_trace(trace, comparable)
    if comparable:
        print(f"COMPARE: same first {comparable} sampling WINDOWS only;"
              " game scenes not synchronized, not a controlled FPS A/B test.")
    print("NO hardware GPU usage / guest hot PC attribution / additional RAM diagnosis"
          " is possible from these counters alone.")

if __name__ == "__main__":
    main()
