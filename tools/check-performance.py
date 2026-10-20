#!/usr/bin/env python3
"""Verify maintained guest JIT profiles and production diagnostic hot-path guards."""
from pathlib import Path
import json
import shlex

root = Path(__file__).resolve().parents[1]
cache = Path((root / '.local/headless-cache').read_text().strip())
generated = cache / 'native-local/headless'
cache_text = (generated.parent / 'CMakeCache.txt').read_text()
development = 'EDEN_DEV_PROFILE:BOOL=ON' in cache_text
shared_jit_enabled = 'EDEN_SHARED_JIT:BOOL=ON' in cache_text
compile_batch_enabled = 'EDEN_JIT_COMPILE_BATCH:BOOL=ON' in cache_text

# Only the copied dependency interfaces still live under .local.
# G11/X06's complete guest JIT wrappers are now maintained sources.
for name in ('a32_interface.cpp', 'a64_interface.cpp', 'block_of_code.cpp'):
    source = (generated / name).read_text()
    assert 'Eden::Performance::Timer' not in source
    assert 'Eden::Performance::SampleCpu' not in source
    assert 'Eden::Performance::cpu_state' not in source

# Verify ALL maintained owners, not stale pre-G11 generated wrapper files.
cmake = (root / 'headless/CMakeLists.txt').read_text()
assert 'list(APPEND core_sources "${EDEN_G11_SOURCE}")' in cmake
assert 'write_derived("${derived}"' not in cmake
jit_root = root/'vendor/encore-active/eden-core/src/core/arm/dynarmic/g11'
for bits in (32, 64):
    for platform in ('host','native'):
        for profile in ('normal','dev'):
            wrapper = (jit_root/f'arm_dynarmic_{bits}_{platform}_{profile}.cpp').read_text()
            expected_samples = 2 if profile == 'dev' else 0
            assert 'Eden::Performance::Timer' not in wrapper
            assert wrapper.count('::Eden::Performance::SampleCpu(') == expected_samples
            assert wrapper.count('::Eden::Performance::cpu_state[m_core_index].phase.store(') == expected_samples
            assert ('CpuPhase::Guest' in wrapper) == (profile == 'dev')
            assert ('CpuPhase::Kernel' in wrapper) == (profile == 'dev')
            assert (f'EDEN_DEV_JIT bits={bits}' in wrapper) == (profile == 'dev')
            assert 'config.code_cache_size = std::uint32_t(8_MiB);' in wrapper
            baseline = (
                'm_core_index == 0 ? 256_MiB : m_core_index < 3 ? 192_MiB : 16_MiB'
                if bits == 64 else
                'm_core_index == 0 ? 512_MiB : m_core_index < 3 ? 64_MiB : 16_MiB'
            )
            if platform == 'native':
                assert baseline in wrapper
                assert f'A{bits}CacheBytes(m_core_index' in wrapper
                assert 'ConstructWithCapacityFallback(' in wrapper
                assert wrapper.count('if (!CheckMemoryAccess(vaddr') == (4 if bits == 32 else 5)
            else:
                # Host fixtures retain the reviewed 512 -> 16 MiB x64
                # reduction; PS5's asymmetric budgets are native-only.
                pinned = (root / f'vendor/sources/eden/src/core/arm/dynarmic/arm_dynarmic_{bits}.cpp').read_text()
                def cache_policy(text):
                    return text.split('    // Code cache size\n', 1)[1].split(
                        '    // Allow memory fault handling', 1)[0]
                expected_policy = cache_policy(pinned)
                assert expected_policy.count('std::uint32_t(512_MiB)') == 1
                expected_policy = expected_policy.replace(
                    'std::uint32_t(512_MiB)', 'std::uint32_t(16_MiB)')
                assert cache_policy(wrapper) == expected_policy
                assert f'A{bits}CacheBytes(m_core_index' not in wrapper
                assert 'ConstructWithCapacityFallback(' not in wrapper
                assert 'if (!CheckMemoryAccess(vaddr' not in wrapper

jit = (generated / 'a64_interface.cpp').read_text()
interface_root = root / 'vendor/encore-active/eden-core/src/dynarmic/backend/x64'
selected = 'a64_interface_shared.cpp' if shared_jit_enabled else 'a64_interface_standard.cpp'
assert jit == (interface_root / selected).read_text(), 'configured A64 owner differs'
# Complete units now contain guarded batch/DEV code even when disabled.
# Check the actual command definitions, rather than absence from raw C++.
records = json.loads((generated.parent / 'compile_commands.json').read_text())
entries = [row for row in records if Path(row['file']).resolve() == (generated / 'a64_interface.cpp').resolve()]
assert len(entries) == 1, 'expected one configured A64 compilation'
argv = entries[0].get('arguments') or shlex.split(entries[0]['command'])
assert '-DPS5_NATIVE=1' in argv
assert ('-DEDEN_JIT_A64_BATCH=1' in argv) == compile_batch_enabled
assert ('-DEDEN_JIT_A64_DEV_PROFILE=1' in argv) == development
if not development:
    # Shipping builds must be the stability path: ordinary per-core Dynarmic, one block per miss.
    assert not shared_jit_enabled
    assert not compile_batch_enabled
    assert 'JitGroup' not in jit
    assert 'const auto entrypoint = emitter.Emit(ir_block).entrypoint;' in jit
    assert 'return entrypoint;' in jit
block = jit.split('    CodePtr GetBlock(', 1)[1].split(
    '    void PerformRequestedCacheInvalidation', 1)[0]
for statement in (
    'A64::Translate(ir_block, arch_descriptor, get_code,',
    'Optimization::Optimize(ir_block, conf, polyfill_options);',
):
    assert statement in block
if shared_jit_enabled:
    assert 'const auto emitted = emitter.Emit(ir_block, false);' in block
elif compile_batch_enabled:
    assert 'const auto entrypoint = emitter.Emit(ir_block, false).entrypoint;' in block
else:
    assert 'const auto entrypoint = emitter.Emit(ir_block).entrypoint;' in block
    assert 'return entrypoint;' in block

# Null-JIT baseline and diagnostics are checked in all eight owned wrappers.

cmake = (root / 'headless/CMakeLists.txt').read_text()
assert 'Timer read_timer' not in cmake
assert 'Timer compile_timer' not in cmake
assert 'protection_timer' not in cmake
shared_root = root / 'vendor/encore-active/eden-core/dynarmic/shared-jit'
shared_jit = (shared_root / 'jit_group_support.inc').read_text()
assert 'bool eden_jit_shared = false;' in shared_jit
assert 'option(EDEN_SHARED_JIT "Enable the experimental cross-core A64 JIT" OFF)' in cmake
assert 'option(EDEN_JIT_COMPILE_BATCH "Compile bounded A64 successor chains on a cache miss" OFF)' in cmake
jit_group = (shared_root / 'jit_group.h').read_text()
jit_impl = (shared_root / 'jit_impl.inc').read_text()
# Production JIT waits must yield the CPU after their short spin. On PS5 real-time workers,
# std::this_thread::yield() can repeatedly reschedule the waiter and starve the owner.
assert 'std::this_thread::yield()' not in jit_group
assert 'std::this_thread::yield()' not in jit_impl
assert 'sleep_for(std::chrono::microseconds(50))' in jit_group
assert 'sleep_for(std::chrono::microseconds(50))' in jit_impl
assert 'EDEN_JIT_CLEAR_BEGIN' in jit_impl and 'EDEN_JIT_CLEAR_END' in jit_impl
monitor_lock = (root / 'vendor/encore-active/eden-core/src/dynarmic/common/spin_lock_x64.cpp').read_text()
assert 'sceKernelUsleep(50);' in monitor_lock
main = (root / 'headless/main.cpp').read_text()
assert 'Performance::Reset()' not in main
assert 'Performance::Report()' not in main
assert 'Settings::values.renderer_debug = false;' in main
print('ENCORE_G11_MAINTAINED_PERFORMANCE_PROFILE_PASS profiles=8')
print('ARM32/ARM64 JIT budgets and development-only CPU sampling PASS')
