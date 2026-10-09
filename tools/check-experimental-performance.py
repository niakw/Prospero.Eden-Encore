#!/usr/bin/env python3
"""Shared PS5 performance policy and development-only tracing contracts.

The completed A/B/C/D campaign is preserved as history; user-facing runtime
no longer selects those experimental JIT tiers.
This source contract does NOT validate firmware performance.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
read = lambda name: (root / name).read_text()
header = read("headless/experimental_performance.h")
main = read("headless/main.cpp")
cmake = read("headless/CMakeLists.txt")
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

assert 'ConfigFile("experiments.json")' in main
assert "if (!safe_launch)" in main
assert 'doc.find("defaults")' in main
assert 'doc.contains(at) && doc.at(at).is_object()' in main
assert 'if (game_options)' in main and 'if (defaults)' in main
assert main.index('if (game_options)') < main.index('if (defaults)')
assert 'get("cpu_placement") == "logical"' in main
assert 'get("vulkan_pacing") == "trace"' in main
assert "EnableExperimentalLogicalPlacement();" in main
assert 'jit == "balanced"' not in main and 'jit == "expanded"' not in main
assert "ChooseJitMemoryPlan(" in main and "ApplyJitMemoryPlan(" in main
# Every explicit sparse JIT allocation is sparse-or-fail, never dense.
# CommitSparseJitCode itself verifies the region with the native mutex;
# do not lock/lookup the same code pointer twice for each compiled block.
assert "IsSparseJitCode(getCode())" not in cmake
assert "::Common::CommitSparseJitCode(const_cast<u8*>(getCode()), written + codesize)" in cmake
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

assert "A64CacheBytes(m_core_index" in cmake
assert "A32CacheBytes(m_core_index" in cmake
assert 'string(PREPEND wrapper "#include' in cmake
assert "experimental_performance.h" in cmake
assert 'option(EDEN_SHARED_JIT "Enable the experimental cross-core A64 JIT" OFF)' in cmake
assert 'option(EDEN_JIT_COMPILE_BATCH "Compile bounded A64 successor chains on a cache miss" OFF)' in cmake

assert "EnableExperimentalLogicalPlacementImpl" in cpu
assert "if (count < 7)" in cpu and "physical_verified=0" in cpu
assert "secondary_cpus = secondary;" in cpu
# AMD Zen2/PS5 firmware can expose extended physical topology even when
# x2APIC SMT topology is absent or misleading. Do not trust logical IDs.
topology = cpu.split("void CheckWorkerTopology()", 1)[1].split(
    "void EnableExperimentalLogicalPlacementImpl()", 1)[0]
assert "__get_cpuid_max(0x80000000u, nullptr) >= 0x8000001eu" in topology
assert "vb == 0x68747541u" in topology  # AuthenticAMD
assert "family >= 0x17u && (vc & (1u << 22)) != 0" in topology
assert "__cpuid_count(0x8000001eu, 0, a, b, c, d)" in topology
assert "const unsigned threads_per_core = ((b >> 8) & 255u) + 1u;" in topology
assert "core = ((c & 255u) << 8) | (b & 255u);" in topology
assert "cpuset_getaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1, 8, &verified)" in topology
assert "std::memcmp(&one, &verified, 8)" in topology
assert "if (!decoded && has_x2apic)" in topology
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
assert "**Do not activate the new flags yet on console.**" in guide
assert "Safe Launch" in guide
print("PS5 universal A64/A32 JIT budget and dev-only trace controls: source contracts PASS")
