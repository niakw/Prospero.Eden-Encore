#!/usr/bin/env python3
"""Keep diagnostic collection out of production guest, JIT and storage hot paths."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cache = Path((root / '.local/headless-cache').read_text().strip())
generated = cache / 'native-local/headless'
cache_text = (generated.parent / 'CMakeCache.txt').read_text()
development = 'EDEN_DEV_PROFILE:BOOL=ON' in cache_text
shared_jit_enabled = 'EDEN_SHARED_JIT:BOOL=ON' in cache_text
compile_batch_enabled = 'EDEN_JIT_COMPILE_BATCH:BOOL=ON' in cache_text

# Production Dynarmic and its wrapper must contain no CPU sampling/phase atomics.
# Only EDEN_DEV_PROFILE builds may wrap guest runs with owner-written snapshots.
# Regenerate native-local sources before running this generated-output test; cached
# output from the previous hardware build still contains the removed instrumentation.
for name in ('a32_interface.cpp', 'a64_interface.cpp', 'block_of_code.cpp'):
    source = (generated / name).read_text()
    assert 'Eden::Performance::Timer' not in source
    assert 'Eden::Performance::SampleCpu' not in source
    assert 'Eden::Performance::cpu_state' not in source

for bits in (32, 64):
    wrapper = (generated / f'arm_dynarmic_{bits}.cpp').read_text()
    assert 'Eden::Performance::Timer' not in wrapper
    expected_samples = 2 if development else 0
    assert wrapper.count('::Eden::Performance::SampleCpu(') == expected_samples
    assert wrapper.count('::Eden::Performance::cpu_state[m_core_index].phase.store(') == expected_samples
    if development:
        assert 'CpuPhase::Guest' in wrapper and 'CpuPhase::Kernel' in wrapper

jit = (generated / 'a64_interface.cpp').read_text()
if not development:
    # Shipping builds must be the stability path: ordinary per-core Dynarmic, one block per miss.
    assert not shared_jit_enabled
    assert not compile_batch_enabled
    assert 'JitGroup' not in jit
    assert 'std::array<std::optional<IR::LocationDescriptor>, 32> pending' not in jit
    assert 'return emitter.Emit(ir_block).entrypoint;' in jit
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
    assert 'return emitter.Emit(ir_block).entrypoint;' in block

for bits in (32, 64):
    wrapper = (generated / f'arm_dynarmic_{bits}.cpp').read_text()
    assert ('m_core_index == 0 ? 256_MiB : m_core_index < 3 ? 192_MiB : 16_MiB' if bits == 64 else
            'm_core_index == 0 ? 512_MiB : m_core_index < 3 ? 64_MiB : 16_MiB') in wrapper
    assert 'config.code_cache_size = std::uint32_t(8_MiB);' in wrapper  # Null JIT stays small.
    if development:
        assert f'EDEN_DEV_JIT bits={bits}' in wrapper
        assert 'Eden::Performance::SampleCpu' in wrapper

cmake = (root / 'headless/CMakeLists.txt').read_text()
assert 'Timer read_timer' not in cmake
assert 'Timer compile_timer' not in cmake
assert 'protection_timer' not in cmake
shared_jit = (root / 'headless/dynarmic/jit_group_support.inc').read_text()
assert 'bool eden_jit_shared = false;' in shared_jit
assert 'option(EDEN_SHARED_JIT "Enable the experimental cross-core A64 JIT" OFF)' in cmake
assert 'option(EDEN_JIT_COMPILE_BATCH "Compile bounded A64 successor chains on a cache miss" OFF)' in cmake
jit_group = (root / 'headless/dynarmic/jit_group.h').read_text()
jit_impl = (root / 'headless/dynarmic/jit_impl.inc').read_text()
# Production JIT waits must yield the CPU after their short spin. On PS5 real-time workers,
# std::this_thread::yield() can repeatedly reschedule the waiter and starve the owner.
assert 'std::this_thread::yield()' not in jit_group
assert 'std::this_thread::yield()' not in jit_impl
assert 'sleep_for(std::chrono::microseconds(50))' in jit_group
assert 'sleep_for(std::chrono::microseconds(50))' in jit_impl
assert 'EDEN_JIT_CLEAR_BEGIN' in jit_impl and 'EDEN_JIT_CLEAR_END' in jit_impl
monitor_lock = (root / 'headless/spin-lock.inc').read_text()
assert 'sceKernelUsleep(50);' in monitor_lock
main = (root / 'headless/main.cpp').read_text()
assert 'Performance::Reset()' not in main
assert 'Performance::Report()' not in main
assert 'Settings::values.renderer_debug = false;' in main
print('ARM32/ARM64 JIT budgets and development-only CPU sampling PASS')
