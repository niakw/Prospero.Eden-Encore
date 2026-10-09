#!/usr/bin/env python3
"""Source-only regression: shader pool must not double-reserve CPU slots.

R237 recorded 16 hardware concurrency, 8 allowed secondary CPU slots,
but only ONE shader builder because the old pool deducted seven primary
workers that were ALREADY removed from its inherited secondary mask.
This stages host/source tests only. DO NOT run until user explicitly says GO.
"""
from pathlib import Path
port = (Path(__file__).resolve().parents[0] / "prepare-vulkan-port.py").read_text()
performance = (Path(__file__).resolve().parents[1] / "headless/performance.cpp").read_text()
header = (Path(__file__).resolve().parents[1] / "headless/performance.h").read_text()
begin = port.index("pipeline_worker_replacement = '''")
end = port.index("if shader_source.count(pipeline_worker_anchor)", begin)
policy = port[begin:end]
assert 'pipeline_ps5_headers = f\'\'\'' in port
assert '"{port / \'performance.h\'}"' in port
assert "cpuset_getaffinity(" in policy
assert "::Eden::Performance::PinnedWorkerMask()" in policy
assert "primary_in_mask" in policy
assert "const size_t reserved = affinity_rc == 0 && primary_mask ?" in policy
assert "primary_in_mask + secondary_headroom : unverified_reserved" in policy
assert "constexpr size_t secondary_headroom = 2;" in policy
assert "constexpr size_t unverified_reserved = 7;" in policy
assert "constexpr size_t max_pipeline_workers = 6;" in policy
assert "std::min(spare, max_pipeline_workers)" in policy
assert "spare / 2ULL" not in policy
assert "EDEN_PS5_SHADER_WORKERS reported=" in policy
assert "physical_verified=%u" in policy
assert "std::uint64_t PinnedWorkerMask() noexcept;" in header
assert "if (!worker_topology_ready) return 0;" in performance

def workers(reported: int, allowed: set[int], primary: set[int] | None) -> int:
    schedulable = min(len(allowed), reported) if allowed else min(reported, 4)
    reserved = len(allowed.intersection(primary)) + 2 if primary is not None else 7
    return max(1, min(max(0, schedulable - reserved), 6))

primary = set(range(5))
assert workers(16, set(range(13)), primary) == 6   # full app mask
assert workers(16, set(range(5, 13)), primary) == 6  # PS5 R237 secondary mask
assert workers(16, set(range(5, 13)), None) == 1  # fail-closed unverified
assert workers(16, set(range(10)), primary) == 3
assert workers(16, set(range(13)), None) == 6
assert workers(16, set(range(1, 7)), primary) == 1
assert workers(16, set(), primary) == 1
print("SOURCE POLICY: verified PS5 8-slot secondary affinity uses 6 shader workers, keeps 2 for services")
print("R237 test result still unknown: no build without user authorization")
