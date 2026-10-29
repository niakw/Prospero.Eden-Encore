#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only FC27 cache-contention / frame-pacing audit.

Sampled FPS is an average over several seconds, not a per-frame timing proof.
Only pair EDEN_FRAME_PRESSURE with an immediately preceding EDEN_VULKAN_FRAME
when the exact reported total frame matches; don't extrapolate to log-off runs.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import re
import statistics

FIELDS = re.compile(r"\b([A-Za-z][A-Za-z_0-9]*)=(-?[0-9]+(?:\.[0-9]+)?)")

def values(line: str) -> dict[str, float]:
    return {key: float(value) for key, value in FIELDS.findall(line)}

def windows(lines: list[str]) -> list[dict[str, float]]:
    result = []
    pending = None
    last_row = None  # measured pressure row owning the next four JIT-core records
    jit_cores: dict[int, dict[str, float]] = {}
    for line in lines:
        if "EDEN_VULKAN_FRAME " in line:
            # A new interval cannot inherit core data from an older window.
            last_row = None
            jit_cores = {}
            pending = values(line.partition("EDEN_VULKAN_FRAME ")[2])
        elif "EDEN_FRAME_PRESSURE " in line and pending is not None:
            pressure = values(line.partition("EDEN_FRAME_PRESSURE ")[2])
            # Quiet PS5 runs emit detail=not_measured, and a counter reset
            # emits counters_reset=1. Both carry a valid frame ID but NO
            # measured JIT/cache durations: never report them as zero waits.
            # The production measured record always supplies both fields.
            if (pending.get("total") is not None
                    and pending["total"] == pressure.get("frame")
                    and "cache_wait_ms" in pressure and "jit_ms" in pressure):
                last_row = {**pending, **pressure}
                result.append(last_row)
                jit_cores = {}
            else:
                last_row = None
            pending = None
        elif "EDEN_FRAME_JIT_CORE " in line and last_row is not None:
            core_values = values(line.partition("EDEN_FRAME_JIT_CORE ")[2])
            core = core_values.get("core")
            fields = ("compile_ns", "compile_calls", "evacuations")
            # Accept exactly the four production guest cores, once each, on
            # the SAME measured interval. Partial/mixed sets are not evidence.
            if (core_values.get("frame") != last_row["total"]
                    or core not in (0.0, 1.0, 2.0, 3.0)
                    or any(k not in core_values or core_values[k] < 0 for k in fields)
                    or int(core) in jit_cores):
                last_row = None
                continue
            jit_cores[int(core)] = core_values
            if len(jit_cores) == 4:
                cpu_ms = sum(x["compile_ns"] for x in jit_cores.values()) / 1_000_000
                # The aggregate is formatted to three decimals in the PS5
                # log. Reject an inconsistent quartet rather than inventing
                # a CPU attribution by joining unrelated messages.
                if abs(cpu_ms - last_row["jit_ms"]) <= 0.001:
                    last_row["jit_core_cpu_sum_ms"] = cpu_ms
                    last_row["jit_core_peak_ms"] = max(
                        x["compile_ns"] for x in jit_cores.values()) / 1_000_000
                    last_row["jit_core_calls"] = sum(
                        x["compile_calls"] for x in jit_cores.values())
                    last_row["jit_core_evacuations"] = sum(
                        x["evacuations"] for x in jit_cores.values())
                last_row = None
    return result

def med(rows: list[dict[str, float]], key: str) -> float | None:
    values_ = [r[key] for r in rows if key in r]
    return statistics.median(values_) if values_ else None

def report(rows: list[dict[str, float]]) -> str:
    if not rows:
        return "NO_VALID_WINDOWS (requires matching frame totals)"
    near30 = [r for r in rows if r.get("fps", 0) >= 29.9]
    slow = [r for r in rows if r.get("fps", 0) < 25]
    groups = [("near30", near30), ("slow_below25", slow)]
    out = [f"all_windows={len(rows)} near30={len(near30)} below25={len(slow)}"]
    for name, subset in groups:
        if not subset:
            continue
        def count(predicate): return sum(bool(predicate(r)) for r in subset)
        out.append(
            f"{name}: n={len(subset)} contended_median={med(subset, 'cache_contended')} "
            f"blocked_ms_median={med(subset, 'cache_wait_ms')} "
            f"cache_ge1000={count(lambda r: r.get('cache_contended', 0)>=1000)} "
            f"worst_over50={count(lambda r: r.get('worst_ms', 0)>50)} "
            f"late38_windows={count(lambda r: r.get('late38', 0)>0)} "
            f"late38_total={sum(r.get('late38', 0) for r in subset):.0f} "
            f"late50_windows={count(lambda r: r.get('late50', 0)>0)} "
            f"max_worst_ms={max(r.get('worst_ms', 0) for r in subset):.3f}"
        )
    # Long-frame triage is observational: cumulative multi-core JIT compile
    # and blocked mutex waits share a reporting window, NOT per-frame identity.
    stable = [r for r in rows if r.get("fps", 0) >= 29.9
              and r.get("worst_ms", float("inf")) < 50]
    extreme = [r for r in rows if r.get("worst_ms", 0) >= 300]
    low_cache = [r for r in extreme if "cache_wait_ms" in r
                 and r["cache_wait_ms"] < 10]
    high_jit = [r for r in extreme if r.get("jit_ms", 0) >= 500]
    out.append(
        f"long_frame_triage: stable30_worst_below50={len(stable)} "
        f"worst_ge300={len(extreme)} "
        f"worst_ge300_cache_below10ms={len(low_cache)} "
        f"worst_ge300_jit_ge500ms={len(high_jit)} "
        f"median_stable_jit_ms={med(stable, 'jit_ms')} "
        f"median_slow_jit_ms={med(extreme, 'jit_ms')} "
        f"median_stable_cache_ms={med(stable, 'cache_wait_ms')} "
        f"median_slow_cache_ms={med(extreme, 'cache_wait_ms')}"
    )
    core_rows = [r for r in rows if "jit_core_peak_ms" in r]
    if core_rows:
        out.append(
            f"jit_core_breakdown: complete={len(core_rows)}/{len(rows)} "
            f"median_peak_cpu_core_ms={med(core_rows, 'jit_core_peak_ms'):.3f} "
            f"max_peak_cpu_core_ms={max(r['jit_core_peak_ms'] for r in core_rows):.3f} "
            f"sum_cpu_core_ms={sum(r['jit_core_cpu_sum_ms'] for r in core_rows):.3f} "
            f"compile_calls={sum(r['jit_core_calls'] for r in core_rows):.0f} "
            f"evacuations={sum(r['jit_core_evacuations'] for r in core_rows):.0f}"
        )
    else:
        out.append(f"jit_core_breakdown: complete=0/{len(rows)} (not measured or incomplete)")
    out.append("NOTE: per-core JIT CPU time may overlap between cores; its maximum "
               "is NOT renderer wall time or the cause of a presentation gap.")
    out.append("NOTE: JIT and cache times aggregate many guest threads across "
               "a reporting window; concurrent peaks do not establish the "
               "precise cause of an individual late frame.")
    out.append("NOTE: try_lock failures are instrumented, not per-frame mutex latency; "
               "blocked_ms sums waits across guest threads. FPS near 30 is not smoothness.")
    return "\n".join(out)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.logs:
        print(path)
        print(report(windows(path.read_text(encoding="utf-8", errors="replace").splitlines())))

if __name__ == "__main__":
    main()
