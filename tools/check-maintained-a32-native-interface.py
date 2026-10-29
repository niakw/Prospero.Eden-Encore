#!/usr/bin/env python3
"""Native A32 JIT must be the exact legacy transform, selected by CMake copy."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/a32_interface.cpp").read_text()
maintained=root/"vendor/encore-active/eden-core/src/dynarmic/backend/x64/a32_interface_native.cpp"
cm=(root/"headless/CMakeLists.txt").read_text()
prefix=(
  "#include <cstdio>\n#include <new>\n"
  'extern "C" void eden_jit_block(unsigned core, unsigned long long location, const void* entry, unsigned long long size) __attribute__((weak));\n'
)
pressure="            invalidate_entire_cache = true;"
pressure_replacement=(
 '            static thread_local unsigned pressure_count;\n'
 '            if (++pressure_count <= 3) std::printf("EDEN_JIT_PRESSURE bits=32 core=%u capacity=%u remaining=%zu\\n", unsigned(conf.processor_id), unsigned(conf.code_cache_size), block_of_code.SpaceRemaining());\n'
 '            // Publish the full-clear request under invalidation_mutex;\n'
 '            // concurrent range invalidations must not race with cache pressure.\n'
 '            ClearCache();'
)
commit="        block_of_code.EnsureMemoryCommitted(MINIMUM_REMAINING_CODESIZE);"
retry=(
 '        try {\n'
 '            block_of_code.EnsureMemoryCommitted(MINIMUM_REMAINING_CODESIZE);\n'
 '        } catch (const std::bad_alloc&) {\n'
 '            // Publish the full-clear request under invalidation_mutex;\n'
 '            // concurrent range invalidations must not race with cache pressure.\n'
 '            ClearCache();\n'
 '            PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);\n'
 '            block_of_code.EnsureMemoryCommitted(MINIMUM_REMAINING_CODESIZE);\n'
 '        }'
)
emit="        return emitter.Emit(ir_block);\n    }"
metered=(
 '        const auto emitted = emitter.Emit(ir_block);\n'
 '        if (eden_jit_block)\n'
 '            eden_jit_block(unsigned(conf.processor_id), descriptor.Value(), reinterpret_cast<const void*>(emitted.entrypoint), emitted.size);\n'
 '        return emitted;\n    }'
)
extent_original = '''    void InvalidateCacheRange(std::uint32_t start_address, std::size_t length) {
        std::unique_lock lock{invalidation_mutex};
        invalid_cache_ranges.add(boost::icl::discrete_interval<u32>::closed(start_address, static_cast<u32>(start_address + length - 1)));
        HaltExecution(HaltReason::CacheInvalidation);
    }'''
extent_checked = '''    void InvalidateCacheRange(std::uint32_t start_address, std::size_t length) {
        if (length == 0) {
            return;
        }
        std::unique_lock lock{invalidation_mutex};
        // A pending full clear already supersedes every narrower invalidation.
        if (!invalidate_entire_cache) {
            // A wrapped or unrepresentable A32 range must not leave stale compiled blocks.
            if (length - 1 > (~u32{0} - start_address)) {
                invalidate_entire_cache = true;
            } else {
                const u32 end_address = start_address + static_cast<u32>(length - 1);
                invalid_cache_ranges.add(boost::icl::discrete_interval<u32>::closed(start_address, end_address));
            }
        }
        HaltExecution(HaltReason::CacheInvalidation);
    }'''
assert source.count(extent_original) == 1, "pinned A32 invalidate extent changed"
for anchor in (pressure,commit,emit):
    assert source.count(anchor)==1,("pinned A32 interface changed",anchor)
expected=prefix+source.replace(pressure,pressure_replacement).replace(commit,retry).replace(emit,metered).replace(extent_original,extent_checked)
# Reviewed on 22 October: detach the JIT invalidation publication mutex
# before executing cache/code invalidations. Pinned third-party input stays fixed.
old_cache_drain = """    void PerformRequestedCacheInvalidation(HaltReason hr) {
        if (Has(hr, HaltReason::CacheInvalidation)) {
            std::unique_lock lock{invalidation_mutex};

            ClearHalt(HaltReason::CacheInvalidation);

            if (!invalidate_entire_cache && invalid_cache_ranges.empty()) {
                return;
            }

            jit_state.ResetRSB();
            if (invalidate_entire_cache) {
                block_of_code.ClearCache();
                emitter.ClearCache();
            } else {
                emitter.InvalidateCacheRanges(invalid_cache_ranges);
            }
            invalid_cache_ranges.clear();
            invalidate_entire_cache = false;
        }
    }"""
new_cache_drain = """    void PerformRequestedCacheInvalidation(HaltReason hr) {
        if (Has(hr, HaltReason::CacheInvalidation)) {
            // Consume the pending request under its mutex, but never hold it
            // while invalidating compiled blocks or changing RX/RW code state.
            // A concurrent guest write can queue the NEXT request while this
            // JIT thread processes the current snapshot.
            bool clear_all = false;
            boost::icl::interval_set<u32> ranges;
            {
                std::unique_lock lock{invalidation_mutex};
                ClearHalt(HaltReason::CacheInvalidation);
                clear_all = invalidate_entire_cache;
                invalidate_entire_cache = false;
                ranges.swap(invalid_cache_ranges);
            }

            if (!clear_all && ranges.empty()) {
                return;
            }

            jit_state.ResetRSB();
            if (clear_all) {
                block_of_code.ClearCache();
                emitter.ClearCache();
            } else {
                emitter.InvalidateCacheRanges(ranges);
            }
        }
    }"""
assert expected.count(old_cache_drain) == 1, "pinned A32 cache drain changed"
expected = expected.replace(old_cache_drain, new_cache_drain)
# F07 J01: keep the pinned A32 transformation strict while reproducing
# the native DEV-only A32 timing hooks (and the rare cache-pressure event).
# These exact blocks are deliberately embedded rather than read back from
# maintained: changing or omitting any instrumentation fails parity.
def append_after_exact(anchor: str, addition: str) -> None:
    global expected
    assert expected.count(anchor) == 1, ("A32 profile anchor drift", anchor)
    expected = expected.replace(anchor, anchor + addition)

append_after_exact("#include <new>\n", "#if defined(EDEN_JIT_A32_DEV_PROFILE)\n#include <chrono>\nextern \"C\" bool eden_native_detailed_logging() noexcept __attribute__((weak));\nextern \"C\" void eden_jit_compile(unsigned core, unsigned long long ns) __attribute__((weak));\nextern \"C\" void eden_jit_phases(unsigned core, unsigned long long translate,\n                                unsigned long long optimize, unsigned long long emit,\n                                unsigned long long location) __attribute__((weak));\nextern \"C\" void eden_jit_cache_event(unsigned core, unsigned kind) __attribute__((weak));\n#endif\nextern \"C\" void eden_jit_evacuation(unsigned core) __attribute__((weak));\n")
append_after_exact("        if (auto block = emitter.GetBasicBlock(descriptor))\n            return *block;\n", "#if defined(EDEN_JIT_A32_DEV_PROFILE)\n        // A32 cold misses must contribute to the same four-core witness as\n        // A64. Neither a cache hit nor quiet/release mode reads a clock.\n        struct EdenCompileTimer {\n            unsigned core;\n            bool active;\n            std::chrono::steady_clock::time_point start{};\n            explicit EdenCompileTimer(unsigned c) : core(c),\n                active(eden_native_detailed_logging && eden_native_detailed_logging()) {\n                if (active) start = std::chrono::steady_clock::now();\n            }\n            ~EdenCompileTimer() {\n                if (active && eden_jit_compile)\n                    eden_jit_compile(core, static_cast<unsigned long long>(\n                        std::chrono::duration_cast<std::chrono::nanoseconds>(\n                            std::chrono::steady_clock::now() - start).count()));\n            }\n        } eden_compile_timer{unsigned(conf.processor_id)};\n#endif\n")
append_after_exact("            if (++pressure_count <= 3) std::printf(\"EDEN_JIT_PRESSURE bits=32 core=%u capacity=%u remaining=%zu\\n\", unsigned(conf.processor_id), unsigned(conf.code_cache_size), block_of_code.SpaceRemaining());\n", "            // Match the A64 code-pressure event (not per-block clock work).\n            if (eden_jit_evacuation) eden_jit_evacuation(unsigned(conf.processor_id));\n")
append_after_exact("        ir_block.Reset(arch_descriptor);\n", "#if defined(EDEN_JIT_A32_DEV_PROFILE)\n        const bool eden_phase_timing = eden_compile_timer.active && eden_jit_phases;\n        const auto eden_phase_begin = eden_phase_timing ? std::chrono::steady_clock::now() :\n            std::chrono::steady_clock::time_point{};\n#endif\n")
append_after_exact("        A32::Translate(ir_block, arch_descriptor, conf.callbacks, {conf.arch_version, conf.define_unpredictable_behaviour, conf.hook_hint_instructions});\n", "#if defined(EDEN_JIT_A32_DEV_PROFILE)\n        const auto eden_phase_translated = eden_phase_timing ? std::chrono::steady_clock::now() :\n            std::chrono::steady_clock::time_point{};\n#endif\n")
append_after_exact("        Optimization::Optimize(ir_block, conf, polyfill_options);\n", "#if defined(EDEN_JIT_A32_DEV_PROFILE)\n        const auto eden_phase_optimized = eden_phase_timing ? std::chrono::steady_clock::now() :\n            std::chrono::steady_clock::time_point{};\n#endif\n")
append_after_exact("        const auto emitted = emitter.Emit(ir_block);\n", "#if defined(EDEN_JIT_A32_DEV_PROFILE)\n        if (eden_phase_timing) {\n            const auto eden_phase_emitted = std::chrono::steady_clock::now();\n            const auto eden_ns = [](auto a, auto b) {\n                return static_cast<unsigned long long>(\n                    std::chrono::duration_cast<std::chrono::nanoseconds>(b - a).count());\n            };\n            eden_jit_phases(unsigned(conf.processor_id),\n                            eden_ns(eden_phase_begin, eden_phase_translated),\n                            eden_ns(eden_phase_translated, eden_phase_optimized),\n                            eden_ns(eden_phase_optimized, eden_phase_emitted),\n                            descriptor.Value());\n        }\n#endif\n")
append_after_exact("                emitter.InvalidateCacheRanges(ranges);\n            }\n", "#if defined(EDEN_JIT_A32_DEV_PROFILE)\n            // This clear/range belongs to the snapshot actually consumed.\n            if (eden_native_detailed_logging && eden_native_detailed_logging() &&\n                eden_jit_cache_event) {\n                eden_jit_cache_event(unsigned(conf.processor_id),\n                                     clear_all ? 0u : 1u);\n            }\n#endif\n")
assert maintained.read_text()==expected, "A32 maintained source must exactly match pinned transform plus exact DEV instrumentation"
assert 'write_derived("${PORT_BUILD_DIR}/a32_interface.cpp"' not in cm
assert 'configure_file("${EDEN_MAINTAINED_A32_INTERFACE}"' in cm
assert shutil.which("cmake"),"CMake required for selection proof"
start=cm.index('    set(EDEN_MAINTAINED_A32_INTERFACE\n')
end=cm.index('    get_target_property(jit_sources dynarmic SOURCES)',start)
selection=cm[start:end]
with tempfile.TemporaryDirectory(prefix="encore-a32-native-") as tmp:
    d=Path(tmp)
    dst=d/"build"
    dst.mkdir()
    script=d/"stage.cmake"
    script.write_text(
        "cmake_minimum_required(VERSION 3.25)\n"
        +f'set(PORT_ROOT "{root.as_posix()}")\n'
        +f'set(PORT_BUILD_DIR "{dst.as_posix()}")\n'
        +selection
    )
    subprocess.run(["cmake","-P",str(script)],check=True,timeout=30)
    assert (dst/"a32_interface.cpp").read_bytes()==maintained.read_bytes()
print("ENCORE_A32_NATIVE_INTERFACE_PASS pinned_transform=exact source_selection=1")
