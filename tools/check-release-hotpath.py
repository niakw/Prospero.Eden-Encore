#!/usr/bin/env python3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
cmake=(root/'headless/CMakeLists.txt').read_text()
main=(root/'headless/main.cpp').read_text()
perf=(root/'headless/performance.cpp').read_text()
# The runtime is no longer patched from CMake string fragments.
# Separate complete, maintained A64 source owners must enforce DEV profiling
# without losing the native allocation fallback in the shipping variant.
assert 'if(PS5_NATIVE)\n    set(EDEN_G11_PLATFORM native)' in cmake
assert 'if(EDEN_DEV_PROFILE)\n    set(EDEN_G11_PROFILE dev)\nelse()\n    set(EDEN_G11_PROFILE normal)' in cmake
assert 'arm_dynarmic_${bits}_${EDEN_G11_PLATFORM}_${EDEN_G11_PROFILE}.cpp' in cmake
assert 'if(NOT EXISTS "${EDEN_G11_SOURCE}")' in cmake
assert 'list(REMOVE_ITEM core_sources "${relative}")' in cmake
assert 'list(APPEND core_sources "${EDEN_G11_SOURCE}")' in cmake
normal=(root/'vendor/encore-active/eden-core/src/core/arm/dynarmic/g11/arm_dynarmic_64_native_normal.cpp').read_text()
dev=(root/'vendor/encore-active/eden-core/src/core/arm/dynarmic/g11/arm_dynarmic_64_native_dev.cpp').read_text()
for code in (normal, dev):
    assert 'JitStartup::ConstructWithCapacityFallback(' in code
assert 'Performance::SampleCpu(' not in normal
assert 'Performance::SampleCpu(' in dev
assert '#include "performance.h"' not in normal
assert '#include "performance.h"' in dev
# A final build must be rejected if any experimental JIT or DEV profile is ON.
assert 'if(EDEN_FINAL_RELEASE_PROFILE)' in cmake
assert 'if(EDEN_SHARED_JIT OR EDEN_JIT_COMPILE_BATCH OR' in cmake
assert 'EDEN_SPARSE_JIT_DEV' not in cmake
assert 'EDEN_INLINE_EXCLUSIVES OR EDEN_DEV_PROFILE OR EDEN_DEV_VULKAN OR' in cmake
start=main.index('// Shipping path: no periodic profiler/watchdog work')
end=main.index('#endif',start)
release=main[start:end]
assert 'Performance::Snapshot()' not in release
assert 'completion->wake.wait(lock, completed);' in release
assert 'filter.ParseFilterString("*:Debug")' not in main
assert 'release logging unchanged\\n", stderr);' in main
for forbidden in ('ReleasePcSignal', 'EnableReleasePcSignal', 'release_guest_threads', 'release_guest_pcs'):
    assert forbidden not in perf, forbidden
print('Shipping PS5 hot path diagnostics stripped: PASS')
