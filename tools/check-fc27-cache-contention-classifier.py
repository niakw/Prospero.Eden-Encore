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
assert module.report([]) == "NO_VALID_WINDOWS (requires matching frame totals)"
print("PINNED_FC27_LONG_FRAME_CLASSIFIER_PASS")
