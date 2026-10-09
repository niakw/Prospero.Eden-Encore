#!/usr/bin/env python3
"""Source-only PS5 Vulkan pipeline builder admission policy.

The OS-logical CPU mask is not a physical-core map. These checks keep guest,
GPU and audio/service scheduling headroom without silently halving all spare
logical slots a second time. Hardware FPS, heat and shader timings remain
unverified until an explicitly authorized native build.
"""
from pathlib import Path

port = (Path(__file__).resolve().parents[0] / "prepare-vulkan-port.py").read_text()
begin = port.index("pipeline_worker_replacement = '''")
end = port.index("if shader_source.count(pipeline_worker_anchor)", begin)
policy = port[begin:end]

assert "cpuset_getaffinity(" in policy
assert "constexpr size_t guest_and_gpu_slots = 6;" in policy
assert "constexpr size_t audio_and_service_slots = 1;" in policy
assert "constexpr size_t max_pipeline_workers = 6;" in policy
assert "schedulable > reserved ? schedulable - reserved : 0ULL" in policy
assert "std::min(spare, max_pipeline_workers)" in policy
assert "spare / 2ULL" not in policy
assert "EDEN_PS5_SHADER_WORKERS reported=" in policy
assert "reserved=%zu affinity_rc=%d" in policy

def workers(reported: int, available: int) -> int:
    schedulable = min(available, reported) if available else min(reported, 4)
    spare = max(0, schedulable - 7)
    return max(1, min(spare, 6))

assert workers(16, 13) == 6  # FW13.60 captured topology
assert workers(16, 16) == 6  # never schedule 15 builders
assert workers(16, 10) == 3
assert workers(8, 8) == 1
assert workers(16, 0) == 1  # unavailable affinity: no aggressive guess
assert workers(2, 2) == 1
assert workers(16, 13) + 7 <= 13
assert workers(16, 16) + 7 <= 16

print("SOURCE POLICY: native Vulkan shader pool uses available logical CPU slots (13 => 6 workers); SDK/PS5 untested")
