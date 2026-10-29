#!/usr/bin/env python3
"""Host-only regression for exact-frame log pairing and long-frame triage."""
from pathlib import Path
import importlib.util

root = Path(__file__).resolve().parents[1]
path = root / "tools/analyze-ps5-cache-contention.py"
spec = importlib.util.spec_from_file_location("fc27_cache_contention", path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

def record(total: int, fps: float, worst: float, jit: float,
           mutex: float) -> list[str]:
    return [
        f"EDEN_VULKAN_FRAME frames=150 seconds=5 fps={fps:.3f} "
        f"worst_ms={worst:.3f} total={total} late100=1",
        "EDEN_VULKAN_INTERVALS v1=0 v2=150 v3=0 v4plus=0",
        f"EDEN_FRAME_PRESSURE frame={total} gpu_dispatch_ms=1100 "
        f"gpu_idle_ms=3900 cache_wait_ms={mutex:.3f} "
        f"cache_contended=20 jit_ms={jit:.3f}",
    ]

lines = []
lines += record(150, 30, 33.6, 0.2, 18)
lines += record(300, 21.5, 894, 4200, 0.4)
lines += record(420, 23.3, 315, 100, 510)
lines += ["EDEN_VULKAN_FRAME total=580 fps=20 worst_ms=901"]
lines += ["EDEN_FRAME_PRESSURE frame=581 jit_ms=9000 cache_wait_ms=0"]
rows = module.windows(lines)
assert len(rows) == 3
assert {x["total"] for x in rows} == {150.0, 300.0, 420.0}
output = module.report(rows)
for token in (
    "all_windows=3",
    "stable30_worst_below50=1",
    "worst_ge300=2",
    "worst_ge300_cache_below10ms=1",
    "worst_ge300_jit_ge500ms=1",
    "median_stable_jit_ms=0.2",
    "median_slow_jit_ms=2150.0",
    "median_stable_cache_ms=18.0",
    "median_slow_cache_ms=255.2",
    "concurrent peaks do not establish",
):
    assert token in output, (token, output)
assert module.windows(["EDEN_FRAME_PRESSURE frame=10 jit_ms=1"]) == []
# The PS5 quiet path emits only a frame ID, not measured GPU/cache/JIT
# durations. Counter resets are also invalid intervals, not zero waits.
for sentinel in ("detail=not_measured", "counters_reset=1"):
    assert module.windows([
        "EDEN_VULKAN_FRAME total=450 fps=30 worst_ms=34",
        f"EDEN_FRAME_PRESSURE frame=450 {sentinel}",
    ]) == [], sentinel
# Valid measured zeroes must remain valid; requiring strictly positive
# durations would hide genuinely idle windows.
measured_zero = module.windows([
    "EDEN_VULKAN_FRAME total=600 fps=30 worst_ms=34",
    "EDEN_FRAME_PRESSURE frame=600 jit_ms=0 cache_wait_ms=0",
])
assert len(measured_zero) == 1
assert measured_zero[0]["jit_ms"] == measured_zero[0]["cache_wait_ms"] == 0
# Partially parsed diagnostics must not silently invent missing durations.
assert module.windows([
    "EDEN_VULKAN_FRAME total=750 fps=30 worst_ms=34",
    "EDEN_FRAME_PRESSURE frame=750 jit_ms=0",
]) == []
# A real detailed PS5 report writes exactly four per-core deltas after the
# matching aggregate pressure line. Do not interpret their CPU time as
# elapsed renderer time or accept a mixed/partial quartet.
def core_line(frame: int, core: int, ns: int, calls: int, evacs: int) -> str:
    return (f"EDEN_FRAME_JIT_CORE frame={frame} core={core} "
            f"compile_ns={ns} compile_calls={calls} evacuations={evacs}")

quartet = [
    core_line(900, 2, 15_000_000, 3, 0),
    core_line(900, 0, 50_000_000, 1, 0),
    core_line(900, 3, 5_000_000, 4, 2),
    core_line(900, 1, 30_000_000, 2, 1),
]
jit_rows = module.windows(record(900, 22, 500, 100, 4) + quartet)
assert len(jit_rows) == 1
assert jit_rows[0]["jit_core_cpu_sum_ms"] == 100.0
assert jit_rows[0]["jit_core_peak_ms"] == 50.0
assert jit_rows[0]["jit_core_calls"] == 10.0
assert jit_rows[0]["jit_core_evacuations"] == 3.0
jit_report = module.report(jit_rows)
assert "jit_core_breakdown: complete=1/1" in jit_report
assert "median_peak_cpu_core_ms=50.000" in jit_report
assert "compile_calls=10 evacuations=3" in jit_report
assert "NOT renderer wall time" in jit_report
# Missing core, duplicated core, wrong window and mismatch against aggregate
# must all reject an attribution (without discarding the valid frame window).
bad_quartets = [
    quartet[:3],
    quartet[:3] + [quartet[0]],
    quartet[:3] + [core_line(901, 1, 30_000_000, 2, 1)],
    quartet[:3] + [core_line(900, 1, 31_000_000, 2, 1)],
    quartet[:3] + [core_line(900, 4, 30_000_000, 2, 1)],
]
for candidate in bad_quartets:
    candidate_rows = module.windows(record(900, 22, 500, 100, 4) + candidate)
    assert len(candidate_rows) == 1
    assert "jit_core_peak_ms" not in candidate_rows[0]
    assert "jit_core_breakdown: complete=0/1" in module.report(candidate_rows)
# Never attach the end of an older quartet to a new frame with different ID.
mixed_rows = module.windows(record(900, 22, 500, 100, 4) + quartet[:2]
                            + record(901, 24, 300, 100, 5) + quartet[2:])
assert len(mixed_rows) == 2
assert all("jit_core_peak_ms" not in row for row in mixed_rows)
# An unmeasured quiet report cannot acquire a fake CPU attribution.
quiet_rows = module.windows([
    "EDEN_VULKAN_FRAME total=900 fps=30 worst_ms=33",
    "EDEN_FRAME_PRESSURE frame=900 detail=not_measured",
] + quartet)
assert quiet_rows == []
assert module.report([]) == "NO_VALID_WINDOWS (requires matching frame totals)"
print("PINNED_FC27_LONG_FRAME_CLASSIFIER_PASS")
