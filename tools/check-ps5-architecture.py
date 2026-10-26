#!/usr/bin/env python3
"""Offline PS5 architecture source contracts (does not compile or launch PS5 code).

Run from any directory: python3 tools/check-ps5-architecture.py
Checks the single native sparse JIT, actual lifecycle hooks and generated
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
    native_boc = read("vendor/encore-active/eden-core/src/dynarmic/backend/x64/block_of_code_native.cpp")
    a64_unit = read("vendor/encore-active/eden-core/src/dynarmic/backend/x64/a64_interface_standard.cpp")
    a32_native = read("vendor/encore-active/eden-core/src/dynarmic/backend/x64/a32_interface_native.cpp")
    worker_script = read("tools/prepare-vulkan-port.py")
    jit_policy = read("headless/experimental_performance.h")
    native_alloc = read("headless/jit-allocator.h")

    # Distinguish kernel direct-memory enumeration from the newer JIT-owned
    # memory snapshots. The two diagnostics deliberately use different
    # lifecycle hooks; conflating them used to make this guard fail even
    # though all current hooks were wired into real title execution.
    stages = set(re.findall(r'passed\("([A-Za-z_]+)"\)', app))
    stages.update(re.findall(r'passed\(game\s*\?\s*"([A-Za-z_]+)"\s*:\s*"([A-Za-z_]+)"\)', app)[0]
                  if 'passed(game ? "game_loaded" : "nro_loaded")' in app else ())
    direct_marker = 'Eden::Performance::ReportDirectMemoryState(name);'
    jit_marker = 'Eden::Performance::ReportJitCodeState(name);'
    require(direct_marker in app and jit_marker in app, "Missing native memory diagnostics")
    direct_begin = app.rfind('if (std::string_view{name} ==', 0, app.index(direct_marker))
    jit_begin = app.rfind('if (std::string_view{name} ==', 0, app.index(jit_marker))
    direct_stages = set(re.findall(r'std::string_view\{name\} == "([A-Za-z_]+)"',
                                   app[direct_begin:app.index(direct_marker)]))
    jit_stages = set(re.findall(r'std::string_view\{name\} == "([A-Za-z_]+)"',
                                app[jit_begin:app.index(jit_marker)]))
    require(direct_stages == {"core_initialized", "core_shutdown", "core_destroyed"},
            "Wrong direct-memory snapshot stages")
    require(jit_stages == {"game_loaded", "nro_loaded", "cpu_manager_ready", "core_shutdown"},
            "Wrong JIT-owned memory snapshot stages")
    require((direct_stages | jit_stages).issubset(stages),
            "Native memory snapshot references an unreachable lifecycle stage")
    require('Eden::Performance::ReportDirectMemoryState(name);' in app, "Lifecycle call absent")
    require('void ReportDirectMemoryState(const char* phase);' in perf_h, "Lifecycle API declaration absent")
    require('regions < 8192' in perf, "Direct memory traversal is not bounded")
    require('try { std::rethrow_exception(completion->failure); }\n                    catch (const std::bad_alloc&) {' in app,
            "Rendering worker bad_alloc must retain its original type through game shutdown")
    require('} catch (const std::bad_alloc&) {' in app and
            'launch_error = "The game could not allocate PS5 memory. Close Eden Encore completely before retrying to release memory retained between games.";' in app,
            "All-title JIT/VA/heap std::bad_alloc must surface memory recovery hint in the launcher")
    require('EDEN_PS5_OOM largest_query_ok=%u largest_free_mib=%zu' in app and
            'Eden::Performance::QueryLargestDirectMemoryBlock(&oom_largest_free)' in app,
            "Native OOM must record bounded contiguous-direct-memory headroom on failure")
    require('EDEN_HEAP_LIFETIME phase=%s pieces=%zu large=%zu large_blocks=%u tcache=%zu' in perf,
            "Per-title teardown heap retained backing and private-cache snapshots missing")
    require('EDEN_HEAP_PIECE bytes=%zu va=%p pa=%llx alloc_ns=%llu map_ns=%llu zero_ns=%llu' in native,
            "Native heap-piece commit must report OS alloc, map and zeroing costs")
    require('const auto map_rc = sceKernelMapDirectMemory(&at, size,' in native and
            'if (map_rc == 0 && at != address && at && at != MAP_FAILED &&' in native,
            "Native heap mapping mismatch must unmap unexpected owned VA before physical release")
    require('clock_gettime(CLOCK_MONOTONIC' in native and 'std::memset(address, 0, size);' in native,
            "Native heap timing must preserve mandatory zeroed memory")

    require('EDEN_SPARSE_JIT_DEV' not in cmake,
            "Parallel native JIT build modes must not return")
    require('experimental_sparse_jit = true;' in app and
            'if (!Common::ProbeSparseJitAlias())' in app and
            'throw std::runtime_error("PS5 sparse JIT alias preflight failed")' in app,
            "The single native JIT must fail closed when firmware aliases fail")
    require('Common::AllocateMemoryPages(size);' not in native_alloc,
            "The PS5 JIT allocator must not silently fall back to dense memory")
    require('bool ProbeSparseJitAlias() noexcept' in native,
            "Native sparse mapping preflight is missing")
    require('void* unexpected_rw = nullptr;' in native and
            'void* unexpected_rx = nullptr;' in native and
            'if (unexpected_rw && munmap(unexpected_rw, LargePage) != 0)' in native and
            'if (unexpected_rx && munmap(unexpected_rx, LargePage) != 0)' in native,
            "JIT preflight must release unexpected successful VA aliases before physical backing")
    require('std::atomic_thread_fence(std::memory_order_seq_cst);' in native,
            "Alias coherency check is absent")
    require('sceKernelReleaseDirectMemory(physical, LargePage)' in native,
            "Alias probe cleanup is missing")
    require('std::atomic<std::uint64_t> sparse_jit_generation{1};' in native and
            'static thread_local CachedCommit local;' in native and
            'local.generation == generation && local.executable == executable' in native and
            'required <= local.committed' in native and
            'local.committed = region.committed;' in native and
            native.count('sparse_jit_generation.fetch_add(1, std::memory_order_acq_rel);') == 3,
            "Sparse JIT committed-page hints must invalidate on create, trim and release")
    require('::Common::SparseJitUsage(&jit_reserved, &jit_committed)' in perf,
            "Physical JIT memory accounting must target global Common")
    require('#include <algorithm>' in native, "Sparse constructor bootstrap needs std::min")
    require('const std::size_t bootstrap = std::min<std::size_t>(size, 2 * LargePage)' in native,
            "Dynarmic constant pool requires committed pages before construction")
    require('if (!CommitSparseJitCode(rx, bootstrap))' in native and
            'ReleaseSparseJitCode(rx);' in native,
            "Startup bootstrap must clean up failed sparse reservation")
    # Avoid a second global sparse-memory map lock on every translated block.
    # The process-wide selected sparse path is stable for the running title;
    # CommitSparseJitCode itself verifies that the RX address belongs to an
    # actual sparse mapping and fails closed if not.
    require('bool IsSparseJitCode(const void* executable) noexcept' in native and
            '#ifdef PS5_NATIVE' in native_boc and
            '::Common::TrimSparseJitCode(const_cast<u8*>(getCode()), begin)' in native_boc and
            '::Eden::Jit::PlanSparseCommit(written, codesize, maxSize_)' in native_boc and
            '::Common::CommitSparseJitCode(const_cast<u8*>(getCode()), target.bytes)' in native_boc and
            'jit-sparse-commit.h' in native_boc and
            '::Common::IsSparseJitCode(getCode())' not in native_boc,
            "Sparse translated-code commits must validate mapping ownership without per-block duplicate locks")
    require('Mapping{writable, sparse_span, true}' in native_alloc and
            'Common::ReleaseSparseJitCode(pointer)' in native_alloc,
            "The sole native sparse mapping must have one release owner")
    require('EDEN_JIT_SPARSE_MAP_FAILED stage=' in native and
            'MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS' in native and
            'rollback("rw", ENOMEM)' in native and
            'rollback("rx", ENOMEM)' in native and
            'rollback("rx_exec", errno)' in native,
            "Sparse native partial map must restore fixed inaccessible guards")
    require('EDEN_JIT_SPARSE_RESERVE_FAILED bytes=' in native_alloc and
            'fallback=smaller_virtual_arena' in native_alloc and
            'Common::AllocateMemoryPages(size);' not in native_alloc and
            'return nullptr;' in native_alloc,
            "Explicit sparse reservation failure must retry a smaller VA arena, never eagerly allocate all dense RAM")
    require('Common::ReserveSparseJitCode(sparse_span, &writable)' in native_alloc and
            'Common::ReleaseSparseJitCode(executable)' in native_alloc and
            'return static_cast<std::uint8_t*>(writable);' not in native_alloc,
            "Native allocation must be sparse RX/RW or fail without a fallback")
    require('configure_file("${EDEN_BOC_UNIT}" "${PORT_BUILD_DIR}/block_of_code.cpp" COPYONLY)' in cmake and
            'set_property(SOURCE "${PORT_BUILD_DIR}/block_of_code.cpp"' in cmake and
            'TARGET_DIRECTORY dynarmic APPEND PROPERTY COMPILE_DEFINITIONS "PS5_NATIVE=1"' in cmake,
            "Native sparse JIT page commits must be compiled, not excluded by preprocessor")
    require('throw std::bad_alloc{};' in native_boc and
            'block_of_code.EnsureMemoryCommitted(MINIMUM_REMAINING_CODESIZE);' in a64_unit and
            'catch (const std::bad_alloc&)' in a64_unit and
            'catch (const std::bad_alloc&)' in a32_native and
            'configure_file("${EDEN_MAINTAINED_A32_INTERFACE}"' in cmake,
            "A64 and A32 need recoverable one-shot sparse allocation fallback")
    require(a32_native.count('catch (const std::bad_alloc&)') >= 1 and
            a64_unit.count('catch (const std::bad_alloc&)') >= 1,
            "Both guest architectures must recycle committed code pages on OOM")
    require('CountDenseJitDirect(void* writable, bool acquire) noexcept' in native and
            'DenseJitDirectBytes() noexcept' in native,
            "Normal dense JIT physical allocation accounting absent")
    require('Common::CountDenseJitDirect(' not in native_alloc and
            'Common::MapExecutableAlias(' not in native_alloc,
            "The release must not include an alternate dense JIT allocator")
    require('EDEN_JIT_DENSE_MEMORY phase=' in perf and
            '::Common::DenseJitDirectBytes()' in perf,
            "Lifecycle memory must include actual dense JIT residency")
    require(perf.index('void SparseJitUsage(') < perf.index('namespace Eden::Performance {'),
            "JIT memory declaration is inside the wrong C++ namespace")

    # All titles (both guest ISAs) use continuous physical admission.
    require('auto_fc27_jit' not in app and 'fc27-validated-c' not in app,
            "FC27-only JIT selection must not return")
    require('ChooseJitMemoryPlan(' in app and 'ApplyJitMemoryPlan(jit_plan);' in app,
            "Guest launch must select/apply the same JIT memory plan")
    require('bool QueryLargestDirectMemoryBlock(std::size_t* largest) noexcept' in perf,
            "Firmware JIT memory query absent")
    require('QueryLargestDirectMemoryBlock(std::size_t* largest)' in perf_h,
            "Launch-time direct memory query declaration absent")
    require('jit_memory_known = Eden::Performance::QueryLargestDirectMemoryBlock(&jit_largest_free)' in app,
            "Memory admission is not based on kernel availability")
    require('if (safe_launch || !memory_query_ok || largest_free_block <= kHostReserve)' in jit_policy,
            "Safe Launch/unknown memory must use baseline")
    require('kSingleArenaAddressingLimit' in jit_policy,
            "Dynarmic per-arena addressing constraint must be documented")
    require('const std::size_t budget = ((largest_free_block - kHostReserve) / 4)' in jit_policy,
            "JIT must grow with available memory while preserving late-game GPU/guest direct-memory headroom")
    require('plan.a64[0] =' in jit_policy and 'plan.a32[0] =' in jit_policy,
            "Both A64/A32 paths must participate in global budgeting")
    require(jit_policy.count('static_assert(ChooseJitMemoryPlan(') >= 6,
            "Guest JIT admission boundary assertions missing")
    # G11/X06 now selects complete translation units. Check the selected
    # native owners themselves, not the retired CMake source generator.
    require('list(APPEND core_sources "${EDEN_G11_SOURCE}")' in cmake and
            'set_source_files_properties("${EDEN_G11_SOURCE}" TARGET_DIRECTORY core PROPERTIES' in cmake and
            'write_derived("${derived}"' not in cmake,
            "G11 must select maintained JIT sources, never generate C++")
    for bits in (32, 64):
        for profile in ("normal", "dev"):
            unit = read(
                f"vendor/encore-active/eden-core/src/core/arm/dynarmic/g11/"
                f"arm_dynarmic_{bits}_native_{profile}.cpp")
            budget = f"A{bits}CacheBytes(m_core_index"
            require(budget in unit,
                    f"Native A{bits} {profile} wrapper must consume runtime JIT memory budget")
            require('ConstructWithCapacityFallback(' in unit and
                    f"kA{bits}Baseline[m_core_index]" in unit,
                    f"Native A{bits} {profile} startup retry must retain its per-core baseline")
            require(unit.count('if (!CheckMemoryAccess(vaddr') == (4 if bits == 32 else 5),
                    f"Native A{bits} {profile} memory reads must honor abort guards")
    startup = read("headless/jit-startup-retry.h")
    require('target_link_libraries(core PRIVATE xbyak::xbyak)' in cmake,
            "PS5 core wrapper requires pinned private Xbyak target for typed retries")
    require('Xbyak::ERR_CANT_ALLOC' in startup and
            'catch (const std::bad_alloc&)' in startup,
            "Startup retry must only catch actual code allocator failures")
    require('NextCapacity(capacity, baseline)' in startup,
            "A64/A32 cache retry must step toward each core baseline")
    native_start = app.index('#ifdef PS5_NATIVE\n        // One shipping PS5 sparse JIT:')
    native_end = app.index('\n#endif\n#ifdef PS5_NATIVE', native_start)
    require(app.index('ApplyJitMemoryPlan(jit_plan)') > native_end,
            "Native JIT memory policy must be applied after experiment selection")
    require('EDEN_PS5_JIT_POLICY scope=all_titles' in app,
            "Selected JIT policy should be logged once at launch")
    require('jit_cache_tier' not in app and 'tier == 3' not in jit_policy,
            "Retired arbitrary-tier configuration must not return")

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
    print(f"  direct-memory lifecycle: {', '.join(sorted(direct_stages))}")
    print(f"  JIT ownership lifecycle: {', '.join(sorted(jit_stages))}")
    print("  JIT memory: one native sparse allocator, demand commit, quiesced trim, OOM retry")
    print("  all titles: continuous A64/A32 capacities from available direct memory")
    print("  Vulkan: available CPU mask, pinned-source transformation, bounded worker budget")
    print("  Native PS5 compile and firmware 13.60 tests: NOT RUN")


if __name__ == "__main__":
    main()
