#!/usr/bin/env python3
"""Shared PS5 performance policy and development-only tracing contracts.

The completed A/B/C/D campaign is preserved as history; user-facing runtime
no longer selects those experimental JIT tiers.
This source contract does NOT validate firmware performance.
"""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
read = lambda name: (root / name).read_text()
header = read("headless/experimental_performance.h")
main = read("headless/main.cpp")
cmake = read("headless/CMakeLists.txt")
native_boc = read("vendor/encore-active/eden-core/src/dynarmic/backend/x64/block_of_code_native.cpp")
cpu = read("headless/performance.cpp")
graphics = read("headless/graphics.cpp")
graphics_h = read("headless/graphics.h")
performance_h = read("headless/performance.h")
guide = read("docs/FC27_EXPERIMENTS.md")

assert "ChooseJitMemoryPlan(" in header
assert "ApplyJitMemoryPlan(" in header
assert "A64CacheBytes(" in header and "A32CacheBytes(" in header
assert "kSingleArenaAddressingLimit" in header
assert "kHostReserve" in header
assert "std::array<std::atomic<std::uint32_t>,4>" in header
assert "jit_cache_tier{0}" not in header

# One test profile for all games. Legacy per-game experiments.json
# switches must not silently turn off sparse and diagnostic features.
assert 'ConfigFile("experiments.json")' not in main
assert "if (!safe_launch)" in main
assert "experimental_sparse_jit = true;" in main
assert "experimental_logical_cpu = true;" in main
assert "experimental_frame_probe = true;" in main
assert 'if (!Common::ProbeSparseJitAlias())' in main
assert 'throw std::runtime_error("PS5 sparse JIT alias preflight failed")' in main
package=read("tools/build-package.sh")
assert 'EDEN_SPARSE_JIT_DEV' not in package
assert '\ndev)\n' not in package
release=package.split("release|release-stage)\n",1)[1].split("\n    ;;",1)[0]
assert 'export EDEN_SHARED_JIT=OFF EDEN_JIT_COMPILE_BATCH=OFF' in release
assert 'export EDEN_GUEST_WRITE_BRIDGE_DEV=OFF EDEN_UNQUALIFIED_FERMI2D_COPY=OFF' in release
assert 'EDEN_EXPERIMENT_DEFAULTS sparse=%u logical_cpu=%u frame_probe=%u safe=%u' in main
experimental_section = main[main.index('bool experimental_sparse_jit = false;'):main.index('Eden::Experimental::ApplyJitMemoryPlan(jit_plan);')]
assert '#ifdef PS5_NATIVE' in experimental_section
assert '#if defined(PS5_NATIVE) && defined(EDEN_DEV_PROFILE)' not in experimental_section
assert 'EDEN_SPARSE_JIT_DEV' not in experimental_section
assert 'EDEN_SPARSE_JIT_DEV' not in read("tools/build-headless-native.sh")
assert 'EDEN_SPARSE_JIT_DEV' not in cmake
assert 'python3 -B tools/ci/check-release-experiments.py "$EDEN_STAGE_DIR"' in read('.github/workflows/build-040-zbic.yml')
subprocess.run([sys.executable, '-B', str(root / 'tools/ci/check-release-experiments.py'), '--self-test'], check=True)
assert "EnableExperimentalLogicalPlacement();" in main
assert 'jit == "balanced"' not in main and 'jit == "expanded"' not in main
assert "ChooseJitMemoryPlan(" in main and "ApplyJitMemoryPlan(" in main
# Every explicit sparse JIT allocation is sparse-or-fail, never dense.
# CommitSparseJitCode itself verifies the region with the native mutex;
# do not lock/lookup the same code pointer twice for each compiled block.
assert "IsSparseJitCode(getCode())" not in native_boc
assert "::Eden::Jit::PlanSparseCommit(written, codesize, maxSize_)" in native_boc
assert "::Common::CommitSparseJitCode(const_cast<u8*>(getCode()), target.bytes)" in native_boc
assert "EDEN_JIT_SPARSE_PRECOMMIT_CLAMPED" in native_boc
assert "written > maxSize_ || codesize > maxSize_ - written" not in native_boc
assert 'set(EDEN_BOC_UNIT "${EDEN_MAINTAINED_BOC_ROOT}/block_of_code_native.cpp")' in cmake
assert 'configure_file("${EDEN_BOC_UNIT}" "${PORT_BUILD_DIR}/block_of_code.cpp" COPYONLY)' in cmake
jit_alloc = read("headless/jit-allocator.h")
assert "fallback=smaller_virtual_arena" in jit_alloc
assert "Common::ReserveSparseJitCode(sparse_span, &writable)" in jit_alloc
assert "if (!mappings.emplace(pointer," in jit_alloc
# core_initialized precedes title JIT construction; the first useful
# owned-code sample is game_loaded / cpu_manager_ready, never infer 0 RAM
# from a startup-only snapshot. Keep expensive kernel memory enumeration
# away from graphics/present intervals.
assert "void ReportJitCodeState(const char* phase);" in performance_h
assert "void ReportJitCodeState(const char* phase)" in cpu
assert "EDEN_JIT_MEMORY phase=%s sparse_reserved=%zu" in cpu
jit_stage = cpu.split("void ReportJitCodeState(const char* phase)", 1)[1].split(
    "void ReportDirectMemoryState(", 1)[0]
assert "::Common::SparseJitUsage(&reserved, &committed);" in jit_stage
assert "::Common::DenseJitDirectBytes()" in jit_stage
assert "sceKernelDirectMemoryQuery(" not in jit_stage
assert 'std::string_view{name} == "game_loaded"' in main
assert 'std::string_view{name} == "nro_loaded"' in main
assert 'std::string_view{name} == "cpu_manager_ready"' in main
assert "Eden::Performance::ReportJitCodeState(name);" in main

# G11/X06 now compile exact maintained A32/A64 units, not CMake
# rewritten strings. Native code sizing and failure-aware JIT allocation
# must remain present in the source actually selected by core.
assert 'list(APPEND core_sources "${EDEN_G11_SOURCE}")' in cmake
assert 'write_derived("${derived}"' not in cmake
assert 'string(PREPEND wrapper "#include' not in cmake
for bits in (32,64):
    root_src = "vendor/encore-active/eden-core/src/core/arm/dynarmic/g11/"
    native = read(root_src+f"arm_dynarmic_{bits}_native_normal.cpp")
    native_dev = read(root_src+f"arm_dynarmic_{bits}_native_dev.cpp")
    host_src = read(root_src+f"arm_dynarmic_{bits}_host_normal.cpp")
    cache_policy = f"A{bits}CacheBytes(m_core_index"
    assert cache_policy in native and cache_policy in native_dev
    assert cache_policy not in host_src
    assert '#include "experimental_performance.h"' in native
    assert '#include "jit-startup-retry.h"' in native
    assert "ConstructWithCapacityFallback(" in native and "ConstructWithCapacityFallback(" in native_dev
    assert '#include "performance.h"' in native_dev
    assert '#include "performance.h"' not in native
    assert native.count("if (!CheckMemoryAccess(vaddr") == (4 if bits==32 else 5)
print("ENCORE_EXPERIMENTAL_G11_MAINTAINED_SOURCE_OWNER_PASS native_profiles=4")
assert 'option(EDEN_SHARED_JIT "Enable the experimental cross-core A64 JIT" OFF)' in cmake
assert 'option(EDEN_JIT_COMPILE_BATCH "Compile bounded A64 successor chains on a cache miss" OFF)' in cmake

assert "EnableExperimentalLogicalPlacementImpl" in cpu
# The logical-only path cannot prove SMT sibling groups: it must NEVER
# pin owners or constrain unrelated renderer, I/O or service workers.
logical_trial = cpu.split("void EnableExperimentalLogicalPlacementImpl()", 1)[1].split(
    "void PlaceSecondary(", 1)[0]
for invariant in (
    "topology_allowed_valid",
    "allowed_mask",
    "result=skipped",
    "physical_verified=0",
):
    assert invariant in logical_trial, invariant
for forbidden in (
    "worker_cpus =",
    "worker_topology_ready = true;",
    "secondary_cpus =",
    "cpuset_setaffinity(",
    "verified_physical_worker_mask.store",
):
    assert forbidden not in logical_trial, forbidden
# AMD Zen2/PS5 firmware can expose extended physical topology even when
# x2APIC SMT topology is absent or misleading. Do not trust logical IDs.
topology = cpu.split("void CheckWorkerTopology()", 1)[1].split(
    "void EnableExperimentalLogicalPlacementImpl()", 1)[0]
assert "__get_cpuid_max(0x80000000u, nullptr) >= 0x8000001eu" in topology
assert "vb == 0x68747541u" in topology  # AuthenticAMD
assert "family >= 0x17u && (vc & (1u << 22)) != 0" in topology
assert "__cpuid_count(0x8000001eu, 0, a, b, c, d)" in topology
assert "const unsigned threads_per_core = ((b >> 8) & 255u) + 1u;" in topology
assert "amd_cpu_core[cpu] = static_cast<int>(((c & 255u) << 8) | (b & 255u));" in topology
assert "amd_classified == allowed_count" in topology
assert "amd_distinct >= 5 && amd_distinct <= 8" in topology
assert "cpuset_getaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1, 8, &verified)" in topology
assert "std::memcmp(&one, &verified, 8)" in topology
assert "if (has_x2apic)" in topology
assert "x2_cpu_core[cpu] = static_cast<int>(d >> (a & 31u));" in topology
assert "x2_classified == allowed_count" in topology
assert "x2_distinct >= 5 && x2_distinct <= 8" in topology
assert 'source_name = has_amd_topology ? "x2apic_fallback" : "x2apic";' in topology
assert "topology_allowed_valid = true;" in topology
# A failed probe on title B must never inherit pinned workers from title A.
for reset in ("worker_topology_ready = false;", "secondary_cpus = 0;",
              "worker_cpus.fill(0);", "cpu_core.fill(-1);",
              "topology_allowed_valid = false;"):
    assert reset in topology
assert topology.index("worker_topology_ready = false;") < topology.index("cpuset_getaffinity(")
assert topology.index("topology_allowed_valid = false;") < topology.index("cpuset_getaffinity(")
assert "amd_ext=%u x2apic=%u" in topology
# Documented AMD family17h EBX CoreId (same for two SMT siblings), ECX NodeId.
def amd_physical_core(ebx, ecx):
    threads_per_core = ((ebx >> 8) & 255) + 1
    if not 1 <= threads_per_core <= 8:
        return None
    return ((ecx & 255) << 8) | (ebx & 255)
assert amd_physical_core(0x0102, 0) == amd_physical_core(0x0102, 0)  # SMT siblings
assert amd_physical_core(0x0102, 0) != amd_physical_core(0x0103, 0)  # distinct cores
assert amd_physical_core(0x0102, 0) != amd_physical_core(0x0102, 1)  # distinct nodes
assert amd_physical_core(0xff00, 0) is None  # improbable threads/core: fail closed

assert 'EDEN_EXPERIMENT_PRESENT' in graphics
assert "vulkan_frame_probe.load(std::memory_order_relaxed)" in graphics
assert "experimental_pacing_bins" in graphics_h
present = graphics.split("void GraphicsWindow::OnFrameDisplayed()", 1)[1].split(
    "void GraphicsWindow::CheckPresentation(", 1)[0]
assert "std::this_thread::sleep" not in present

assert "0100C49025D3E000" in guide  # historical benchmark identifier only
assert "EDEN_SPARSE_JIT_DEV=ON" in guide and "EDEN_DEV_PROFILE" in guide
assert "**The unified test build requires no experimental options in Settings.**" in guide
assert "Safe Launch" in guide
print("PS5 universal A64/A32 JIT budget and dev-only trace controls: source contracts PASS")
