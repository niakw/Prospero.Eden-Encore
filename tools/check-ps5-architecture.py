#!/usr/bin/env python3
"""Offline PS5 architecture source contracts (does not compile or launch PS5 code).

Run from any directory: python3 tools/check-ps5-architecture.py
Checks developer-only safety gates, actual lifecycle hooks and generated
Vulkan port preparation. Passing is NOT native SDK or hardware qualification.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    app = read("headless/main.cpp")
    native = read("src/memory_pages.cpp")
    perf = read("headless/performance.cpp")
    perf_h = read("headless/performance.h")
    cmake = read("headless/CMakeLists.txt")
    worker_script = read("tools/prepare-vulkan-port.py")
    jit_policy = read("headless/experimental_performance.h")

    stages = set(re.findall(r'passed\("([A-Za-z_]+)"\)', app))
    memory_stages = set(re.findall(r'std::string_view\{name\} == "([A-Za-z_]+)"', app))
    require(memory_stages == {"core_initialized", "core_shutdown"}, "Wrong memory snapshot stages")
    require(memory_stages.issubset(stages), "Memory snapshot references an unreachable lifecycle stage")
    require('Eden::Performance::ReportDirectMemoryState(name);' in app, "Lifecycle call absent")
    require('void ReportDirectMemoryState(const char* phase);' in perf_h, "Lifecycle API declaration absent")
    require('regions < 8192' in perf, "Direct memory traversal is not bounded")

    require('option(EDEN_SPARSE_JIT_DEV "Allow developer-only PS5 sparse JIT cache experiments" OFF)' in cmake,
            "Sparse JIT must not be a shipping build default")
    require('target_compile_definitions(eden-headless PRIVATE EDEN_SPARSE_JIT_DEV=1)' in cmake,
            "Native opt-in compile guard is missing")
    require('#if defined(PS5_NATIVE) && defined(EDEN_DEV_PROFILE)' in app,
            "Experiments JSON must remain developer-only")
    require('#if defined(PS5_NATIVE) && defined(EDEN_SPARSE_JIT_DEV)' in app,
            "Sparse alias preflight must remain gated")
    require('if (experimental_sparse_jit && !Common::ProbeSparseJitAlias())' in app,
            "Sparse JIT alias preflight is missing")
    require('experimental_sparse_jit = false;' in app,
            "Sparse JIT failure must retain the dense fallback")
    require('bool ProbeSparseJitAlias() noexcept' in native,
            "Native sparse mapping preflight is missing")
    require('std::atomic_thread_fence(std::memory_order_seq_cst);' in native,
            "Alias coherency check is absent")
    require('sceKernelReleaseDirectMemory(physical, LargePage)' in native,
            "Alias probe cleanup is missing")
    require('::Common::SparseJitUsage(&jit_reserved, &jit_committed)' in perf,
            "Physical JIT memory accounting must target global Common")
    require(perf.index('void SparseJitUsage(') < perf.index('namespace Eden::Performance {'),
            "JIT memory declaration is inside the wrong C++ namespace")

    # No title-specific performance path: every A64 guest follows the same
    # PS5 admission rule, including a normal non-development release.
    require('auto_fc27_jit' not in app and 'fc27-validated-c' not in app,
            "Legacy FC27-only JIT selection returned")
    require('ChooseA64CacheTier(safe_launch, jit_memory_known, jit_largest_free)' in app,
            "Every game must use the same automatic A64 JIT policy")
    require('bool QueryLargestDirectMemoryBlock(std::size_t* largest) noexcept' in perf,
            "PS5 launch-time direct memory query implementation absent")
    require('QueryLargestDirectMemoryBlock(std::size_t* largest)' in perf_h,
            "PS5 launch-time memory query declaration absent")
    require('jit_memory_known = Eden::Performance::QueryLargestDirectMemoryBlock(&jit_largest_free)' in app,
            "JIT policy does not consult the actual launch-time memory headroom")
    require('if (safe_launch || !memory_query_succeeded) return 0;' in jit_policy,
            "Safe Launch / unknown-memory fallback missing")
    require('largest_free_block >= kExpandedA64Total + kExpandedHeadroom' in jit_policy,
            "C tier must be admitted against actual available memory")
    require('largest_free_block >= kBalancedA64Total + kBalancedHeadroom' in jit_policy,
            "Balanced fallback missing")
    require('if (tier == 2) return (core == 0 ? 320u : 256u) * mib;' in jit_policy,
            "Universal A64 C capacities changed")
    require(jit_policy.count('static_assert(ChooseA64CacheTier(') >= 5,
            "Static policy boundary tests missing")
    dev_start = app.index('#if defined(PS5_NATIVE) && defined(EDEN_DEV_PROFILE)')
    dev_end = app.index('\n#endif\n#if defined(PS5_NATIVE) && defined(EDEN_SPARSE_JIT_DEV)', dev_start)
    require(app.index('jit_cache_tier.store(experimental_jit_cache') > dev_end,
            "JIT policy stores must not be compiled out of normal release builds")
    require('EDEN_PS5_JIT_POLICY scope=all_titles' in app,
            "Release build must report the global policy (once per launch)")
    require('jit == "elastic"' not in app and 'tier == 3' not in jit_policy,
            "Arbitrary 4 GiB experiment must not be reintroduced")

    ast.parse(worker_script, filename="tools/prepare-vulkan-port.py")
    require('cpuset_getaffinity(CPU_LEVEL_WHICH, CPU_WHICH_TID, -1, 8, &allowed)' in worker_script,
            "PS5 Vulkan workers must use actual allowed CPU affinity")
    require('CPU_ISSET(cpu, &allowed)' in worker_script, "Native affinity enumeration missing")
    require('#include <sys/cpuset.h>' in worker_script, "Native CPU affinity SDK header missing")
    require('shader_source.count(pipeline_worker_anchor) != 1' in worker_script,
            "Pinned shader-worker transformation must fail on upstream drift")
    require('EDEN_PS5_SHADER_WORKERS reported=' in worker_script,
            "PS5 shader worker selection diagnostics missing")

    print("PASS PS5_NATIVE_ARCHITECTURE_CONTRACTS")
    print(f"  lifecycle points: {', '.join(sorted(memory_stages))}")
    print("  sparse JIT: compile-gated, startup alias preflight, committed-memory accounting")
    print("  all titles: headroom-gated A64 C/B, conservative fallback; A32 unchanged")
    print("  Vulkan: available CPU mask, pinned-source transformation, bounded worker budget")
    print("  Native PS5 compile and firmware 13.60 tests: NOT RUN")


if __name__ == "__main__":
    main()
