#!/usr/bin/env python3
"""Source-only regression: shader pool must not double-reserve CPU slots.

R237 recorded 16 hardware concurrency, 8 allowed secondary CPU slots,
but only ONE shader builder because the old pool deducted seven primary
workers that were ALREADY removed from its inherited secondary mask.
This stages host/source tests only. DO NOT run until user explicitly says GO.
"""
from pathlib import Path
import ast
port = (Path(__file__).resolve().parents[0] / "prepare-vulkan-port.py").read_text()
performance = (Path(__file__).resolve().parents[1] / "headless/performance.cpp").read_text()
header = (Path(__file__).resolve().parents[1] / "headless/performance.h").read_text()
# Source-text contracts are useless if the Python generator itself cannot
# parse. This caught accidental C++ // comments inserted outside a C++
# triple-quoted replacement on the dev branch before a PS5 build.
ast.parse(port, filename="tools/prepare-vulkan-port.py")
begin = port.index("pipeline_worker_replacement = '''")
end = port.index("if shader_source.count(pipeline_worker_anchor)", begin)
policy = port[begin:end]
assert 'pipeline_ps5_headers = f\'\'\'' in port
assert '"{port / \'performance.h\'}"' in port
assert "cpuset_getaffinity(" in policy
assert "::Eden::Performance::PinnedWorkerMask()" in policy
assert "primary_in_mask" in policy
assert "const size_t reserved = affinity_rc == 0 && primary_mask ?" in policy
assert "secondary_isolated ? secondary_headroom : unverified_reserved" in policy
assert "primary_in_mask + secondary_headroom :" in policy
assert "VerifiedSecondaryPlacementMask()" in policy
assert "(allowed_mask & ~secondary_mask) == 0" in policy
assert "constexpr size_t secondary_headroom = 2;" in policy
assert "constexpr size_t unverified_reserved = 7;" in policy
assert "constexpr size_t max_pipeline_workers = 6;" in policy
assert "const size_t schedulable = available ? available : std::min<size_t>(reported, 4);" in policy
assert "available ? std::min(available, reported)" not in policy
assert "std::min(spare, max_pipeline_workers)" in policy
assert "spare / 2ULL" not in policy
assert "EDEN_PS5_SHADER_WORKERS reported=" in policy
assert "physical_verified=%u" in policy
assert "logical_isolated=%u" in policy
assert "allowed_mask=0x%llx primary_mask=0x%llx" in policy
assert "EDEN_PS5_CPU_ACCESS hardware_reported=" in performance
assert "EDEN_PS5_CPU_PHYSICAL_SUMMARY classified=" in performance
assert "EDEN_PS5_CPU_SPLIT allowed=" in performance
assert "EDEN_PS5_CPU_TOPOLOGY_REJECT reason=more_than_8_physical_ids" in performance
assert "worker_topology_ready = count == cores.size() && physical_ids_plausible;" in performance
assert "std::uint64_t PinnedWorkerMask() noexcept;" in header
assert "std::uint64_t VerifiedSecondaryPlacementMask() noexcept;" in header
assert "std::atomic<std::uint64_t> verified_secondary_placement_mask{0};" in performance
assert "cpuset_getaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1, 8, &actual) == 0" in performance
assert "std::memcmp(&mask, &actual, 8) == 0" in performance
assert "std::atomic<std::uint64_t> verified_physical_worker_mask{0};" in performance
assert "verified_physical_worker_mask.store(0, std::memory_order_release);" in performance
assert "verified_physical_worker_mask.store(verified_mask, std::memory_order_release);" in performance
assert "verified_physical_worker_mask.load(std::memory_order_acquire)" in performance
assert "if (!worker_topology_ready) return 0;" not in performance
assert performance.index("verified_physical_worker_mask.store(verified_mask, std::memory_order_release);") < performance.index("void EnableExperimentalLogicalPlacementImpl()")
assert "worker_topology_ready = true;" in performance  # logical trial is intentionally NOT physical proof

def workers(reported: int, allowed: set[int], primary: set[int] | None,
            secondary: set[int] | None = None) -> int:
    # OS-verified affinity wins over std::thread::hardware_concurrency hint.
    schedulable = len(allowed) if allowed else min(reported, 4)
    isolated = bool(allowed and secondary and allowed.issubset(secondary))
    reserved = (len(allowed.intersection(primary)) + 2 if primary is not None
                else 2 if isolated else 7)
    return max(1, min(max(0, schedulable - reserved), 6))

primary = set(range(5))
assert workers(16, set(range(13)), primary) == 6   # full app mask
assert workers(16, set(range(5, 13)), primary) == 6  # PS5 R237 secondary mask
assert workers(4, set(range(5, 13)), primary) == 6  # OS mask overrides under-reported hint
assert workers(2, set(range(13)), primary) == 6  # no artificial 2-thread hardware cap
assert workers(16, set(range(5, 13)), primary) == 6  # 6 builders + 2 secondary service slots
assert workers(16, set(range(5, 13)), None) == 1  # fail-closed unverified
assert workers(16, set(range(5, 13)), None, set(range(5, 13))) == 6  # verified logical split
assert workers(16, set(range(5, 13)), None, set(range(5, 12))) == 1  # one guest overlap -> refuse
assert workers(16, set(range(5, 13)), None, set()) == 1  # no kernel evidence
assert workers(8, set(range(5, 9)), None, set(range(5, 9))) == 2  # keep two logical service slots
assert workers(16, set(range(10)), primary) == 3
assert workers(16, set(range(13)), None) == 6
assert workers(16, set(range(1, 7)), primary) == 1
assert workers(16, set(), primary) == 2  # successful empty affinity: fallback 4 slots minus 2 headroom
assert workers(16, set(), None) == 1  # unavailable/unverified affinity: reserve 7
print("SOURCE POLICY: verified PS5 logical secondary split permits up to 6 shader workers; fail-closed otherwise")
print("R237 test result still unknown: no build without user authorization")

# Trigger unified PS5 validation/build after the corrected shader worker fallback regression.
