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
# GPU-owner phase samples are printed after the JIT quartet by
# ReportGpuThread. Match exact frame and unique phase; never treat these
# sampled nested durations as the full five-second renderer wall time.
def gpu_phase(frame: int, phase: str, ns: int) -> str:
    return (f"EDEN_GPU_CACHE_PHASE frame={frame} phase={phase} "
            f"samples=50 total_ns=500000000 window_samples=3 "
            f"window_ns={ns} max_ns={ns // 2}")

phase_lines = [
    gpu_phase(930, "compute_pair_wait", 2_000_000),
    gpu_phase(930, "pair_held", 18_000_000),
    gpu_phase(930, "pair_wait", 4_000_000),
    gpu_phase(930, "compute_pair_held", 6_000_000),
]
owner_rows = module.windows(record(930, 29, 125, 100, 3) + phase_lines)
assert len(owner_rows) == 1
assert owner_rows[0]["gpu_pair_held_sample_ms"] == 18.0
assert owner_rows[0]["gpu_compute_pair_held_sample_ms"] == 6.0
assert owner_rows[0]["gpu_pair_wait_samples"] == 3
owner_report = module.report(owner_rows)
assert "gpu_cache_owner_samples: complete=1/1" in owner_report
assert "graphics_held_sample_ms=18.000" in owner_report
assert "compute_held_sample_ms=6.000" in owner_report
assert "graphics_wait_sample_ms=4.000" in owner_report
assert "compute_wait_sample_ms=2.000" in owner_report
assert "sample 1-in-16 draws" in owner_report
# Incomplete, repeated or wrong-frame phase sets must not become a
# misleading complete graphics/compute lock-holder attribution.
bad_phase_sets = [
    phase_lines[:3],
    phase_lines[:3] + [phase_lines[0]],
    phase_lines[:3] + [gpu_phase(931, "compute_pair_held", 6_000_000)],
    phase_lines[:3] + [gpu_phase(930, "compute_pair_held", -1)],
]
for invalid in bad_phase_sets:
    bad_rows = module.windows(record(930, 29, 125, 100, 3) + invalid)
    assert len(bad_rows) == 1
    assert "gpu_cache_owner_samples: complete=0/1" in module.report(bad_rows)
assert module.windows([
    "EDEN_VULKAN_FRAME total=930 fps=30 worst_ms=34",
    "EDEN_FRAME_PRESSURE frame=930 detail=not_measured",
] + phase_lines) == []
# A detailed native snapshot publishes all cold shader stages and both
# Vulkan command-worker wait phases. Require the whole subset for each
# category; do not promote aggregate 5s samples to a per-miss causal trace.
shader = (
    "graphics_pipeline_create", "compute_pipeline_create",
    "graphics_shader_environment", "shader_pool_reset", "shader_cfg",
    "shader_ir", "shader_spirv", "shader_module",
)
worker = ("graphics_pipeline_wait", "compute_pipeline_wait")
assert set(shader) == module.SHADER_PHASES
assert set(worker) == module.WORKER_PHASES
assert module.RING_PHASES == frozenset(("descriptor_ring_finish", "descriptor_ring_preflight"))
# The native PS5 reporter is the source of truth for these phase names.
# Fail if its phase table or frame identifiers drift from this parser.
native_report = (root / "headless/performance.cpp").read_text()
native_frames = (root / "headless/graphics.cpp").read_text()
phase_table = native_report.split("constexpr const char* cache_phase_names[] = {", 1)[1].split("};", 1)[0]
for phase in module.PROFILE_PHASES:
    assert f'"{phase}"' in phase_table, phase
assert "EDEN_GPU_CACHE_PHASE frame=%u phase=%s" in native_report
assert "window_samples=%llu window_ns=%llu max_ns=%llu" in native_report
assert "EDEN_FRAME_JIT_CORE frame=%u core=%u compile_ns=%llu" in native_frames
assert "EDEN_FRAME_PRESSURE frame=%u detail=not_measured" in native_frames
full_phase_lines = [gpu_phase(970, phase, 2_000_000)
                    for phase in (*shader, *worker)]
complete = module.windows(record(970, 27, 95, 100, 3) + full_phase_lines)
assert len(complete) == 1
phase_report = module.report(complete)
assert "shader_phase_samples: complete=1/1" in phase_report
assert "worker_wait_samples: complete=1/1" in phase_report
assert "shader_cfg_sample_ms=2.000" in phase_report
assert "shader_spirv_sample_ms=2.000" in phase_report
assert "graphics_pipeline_wait_samples=3" in phase_report
assert "compute_pipeline_wait_sample_ms=2.000" in phase_report
assert "NOT a causal attribution to one cold miss" in phase_report
assert "do NOT measure GPU-owner shader translation" in phase_report
# A broken/truncated log may supply every shader stage but only one worker
# wait: the shader subset is complete while worker attribution is not.
partial = module.windows(record(970, 27, 95, 100, 3) + full_phase_lines[:-1])
assert len(partial) == 1
assert "shader_phase_samples: complete=1/1" in module.report(partial)
assert "worker_wait_samples: complete=0/1" in module.report(partial)
assert "shader_phase_samples: complete=0/1" in module.report(
    module.windows(record(970, 27, 95, 100, 3) + full_phase_lines[1:])
)
# Duplicated shader stage must prevent acceptance of a full set even if
# all expected names are present once.
duplicate = module.windows(
    record(970, 27, 95, 100, 3) + full_phase_lines[:2] +
    [full_phase_lines[0]] + full_phase_lines[2:]
)
assert "shader_phase_samples: complete=0/1" in module.report(duplicate)
# Reject a duplicate after ALL evidence was initially accepted too: the
# previous complete snapshot must be revoked, not left in the result dict.
late_duplicate = module.windows(
    record(970, 27, 95, 100, 3) + full_phase_lines +
    [gpu_phase(970, "shader_cfg", 2_000_000)]
)
assert "shader_phase_samples: complete=0/1" in module.report(late_duplicate)
assert "worker_wait_samples: complete=0/1" in module.report(late_duplicate)
jit_late_duplicate = module.windows(
    record(900, 22, 500, 100, 4) + quartet +
    [core_line(900, 0, 50_000_000, 1, 0)]
)
assert "jit_core_breakdown: complete=0/1" in module.report(jit_late_duplicate)
# Exact GPU drain phases: unlike the shader draw samples these two timers
# count every real Finish call, separately under paired locks and pre-lock.
drain_lines = [
    gpu_phase(990, "descriptor_ring_finish", 26_000_000),
    gpu_phase(990, "descriptor_ring_preflight", 2_000_000),
]
drain_rows = module.windows(record(990, 24, 170, 100, 4) + drain_lines)
drain_report = module.report(drain_rows)
assert "descriptor_ring_drain: complete=1/1" in drain_report
assert "under_lock_finish_calls=3 under_lock_finish_ms=26.000" in drain_report
assert "prelock_finish_calls=3 prelock_finish_ms=2.000" in drain_report
assert "not 1-in-16 draw samples" in drain_report
# Explicit zero is valid: no fullness waits in this measured window.
zero_drain = [
    "EDEN_GPU_CACHE_PHASE frame=991 phase=descriptor_ring_finish "
    "samples=100 total_ns=0 window_samples=0 window_ns=0 max_ns=0",
    "EDEN_GPU_CACHE_PHASE frame=991 phase=descriptor_ring_preflight "
    "samples=100 total_ns=0 window_samples=0 window_ns=0 max_ns=0",
]
zero_rows = module.windows(record(991, 30, 33, 0, 0) + zero_drain)
zero_report = module.report(zero_rows)
assert "descriptor_ring_drain: complete=1/1" in zero_report
assert "under_lock_finish_calls=0 under_lock_finish_ms=0.000" in zero_report
assert "prelock_finish_calls=0 prelock_finish_ms=0.000" in zero_report
# One missing, duplicate, or foreign-frame line invalidates attribution.
for corrupt in (
    drain_lines[:1],
    drain_lines + [drain_lines[0]],
    drain_lines[:1] + [gpu_phase(992, "descriptor_ring_preflight", 2_000_000)],
):
    candidate = module.windows(record(990, 24, 170, 100, 4) + corrupt)
    assert "descriptor_ring_drain: complete=0/1" in module.report(candidate)
# Frame-housekeeping owner samples are not the graphics/compute draw-pair
# samples. A complete quartet is required, including measured zeroes; never
# mix a frame from another window or silently accept duplicate snapshots.
frame_phases = (
    "frame_texture_wait", "frame_texture_held",
    "frame_buffer_wait", "frame_buffer_held",
)
assert set(frame_phases) == module.FRAME_OWNER_PHASES
frame_lines = [
    gpu_phase(995, "frame_buffer_held", 5_000_000),
    gpu_phase(995, "frame_texture_wait", 2_000_000),
    gpu_phase(995, "frame_buffer_wait", 3_000_000),
    gpu_phase(995, "frame_texture_held", 7_000_000),
]
frame_rows = module.windows(record(995, 22, 175, 100, 4) + frame_lines)
assert len(frame_rows) == 1
assert frame_rows[0]["gpu_frame_texture_held_sample_ms"] == 7.0
assert frame_rows[0]["gpu_frame_buffer_wait_samples"] == 3
frame_report = module.report(frame_rows)
assert "frame_cache_owner_samples: complete=1/1" in frame_report
assert "frame_texture_held_sample_ms=7.000" in frame_report
assert "frame_texture_wait_sample_ms=2.000" in frame_report
assert "frame_buffer_held_sample_ms=5.000" in frame_report
assert "frame_buffer_wait_sample_ms=3.000" in frame_report
assert "1-in-16 completed GPU frames" in frame_report
assert "specific HUD update stalled" in frame_report
for broken in (
    frame_lines[:3],
    frame_lines + [frame_lines[0]],
    frame_lines[:3] + [gpu_phase(996, "frame_texture_held", 7_000_000)],
    frame_lines[:3] + [gpu_phase(995, "frame_texture_held", -1)],
):
    candidate = module.windows(record(995, 22, 175, 100, 4) + broken)
    assert "frame_cache_owner_samples: complete=0/1" in module.report(candidate)
zero_frame = [
    "EDEN_GPU_CACHE_PHASE frame=996 phase=" + phase +
    " samples=0 total_ns=0 window_samples=0 window_ns=0 max_ns=0"
    for phase in frame_phases
]
zero_frame_rows = module.windows(record(996, 30, 33, 0, 0) + zero_frame)
assert "frame_cache_owner_samples: complete=1/1" in module.report(zero_frame_rows)
assert "frame_texture_held_sample_ms=0.000" in module.report(zero_frame_rows)
assert "frame_cache_owner_samples: complete=0/1" in module.report(
    module.windows(record(996, 30, 33, 0, 0) + frame_lines)
)
assert module.windows([
    "EDEN_VULKAN_FRAME total=995 fps=30 worst_ms=34",
    "EDEN_FRAME_PRESSURE frame=995 detail=not_measured",
] + frame_lines) == []
assert module.report([]) == "NO_VALID_WINDOWS (requires matching frame totals)"
print("PINNED_FC27_LONG_FRAME_CLASSIFIER_PASS")
