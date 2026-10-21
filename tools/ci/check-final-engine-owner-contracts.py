#!/usr/bin/env python3
"""Fail closed if any of the three reviewed release owner contracts drift.

This is a selection/source audit, not an FPS benchmark or console test.
"""
from pathlib import Path
import hashlib

root=Path(__file__).resolve().parents[2]
paths={
 "sm": "vendor/encore-active/eden-core/src/core/hle/service/sm/sm.h",
 "thread": "vendor/encore-active/eden-threading/src/core/hle/kernel/k_thread.h",
 "jit": "vendor/encore-active/eden-core/src/dynarmic/backend/x64/a64_interface_standard.cpp",
}
expected={
 "sm": "83e0b7e26a867d578eb869389a807fe3b9c7035b",
 "thread": "e2f359a54cb6b879bdd41f092cf1ea19fb03e4e6",
 "jit": "20362a046adfe89d65225c1822104f2910eeb2c5",
}
def gitblob(data: bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
sources={key:(root/path).read_text() for key,path in paths.items()}
for key,path in paths.items():
    assert gitblob((root/path).read_bytes())==expected[key], (key,"source changed; re-audit")
sm=sources["sm"]
getter=sm.split("std::shared_ptr<T> GetService(",1)[1].split("\n    void InvokeControlRequest(",1)[0]
for invariant in (
 "std::scoped_lock l{lock};",
 "const auto it = registered_services.find(name);",
 "factory = it->second;",
 "std::static_pointer_cast<T>(factory())",
 "Kernel::GetCurrentThread(kernel).IsDummyThread()",
 "std::this_thread::sleep_for(1ms);",
 "Kernel::Svc::SleepThread(",
):
    assert invariant in getter,invariant
assert getter.index("factory = it->second;")<getter.index("std::static_pointer_cast<T>(factory())")
# Service construction must happen AFTER the block closing the map lock.
assert "}\n            if (factory) {" in getter
assert getter.count("SleepThread(")==1
header=sources["thread"]
for invariant in ("std::binary_semaphore m_context_guard{1};",
                  "std::atomic<ThreadState> m_thread_state{};",
                  "m_dummy_thread_cv{}", "m_dummy_thread_mutex{}"):
    assert invariant in header, invariant
thread_cmake=(root/"vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
scheduler=(root/"vendor/encore-active/eden-threading/src/core/hle/kernel/k_scheduler.cpp").read_text()
assert "if(EDEN_BLOCKING_GUEST_CONTEXT_LOCKS)" in thread_cmake
assert 'target_include_directories(core BEFORE PUBLIC "${_encore_thread_root}")' in thread_cmake
assert "m_context_guard.try_acquire()" in scheduler
assert "m_context_guard.release()" in scheduler
jit=sources["jit"]
for invariant in ("#if defined(EDEN_JIT_A64_BATCH)",
                  "#if defined(EDEN_JIT_A64_DEV_PROFILE)",
                  "std::unique_lock lock{invalidation_mutex};",
                  "block_of_code.ClearCache();",
                  "emitter.InvalidateCacheRanges(invalid_cache_ranges);",
                  "if (length - 1 > (~u64{0} - start_address))"):
    assert invariant in jit,invariant
cmake=(root/"headless/CMakeLists.txt").read_text()
for invariant in ("a64_interface_standard.cpp", "a64_interface_shared.cpp",
                  'NOT EDEN_BLOCKING_GUEST_CONTEXT_LOCKS',
                  'EDEN_JIT_A64_BATCH=1', 'EDEN_JIT_A64_DEV_PROFILE=1',
                  'NOT EDEN_A32_FASTMEM'):
    assert invariant in cmake,invariant
preflight=(root/".github/workflows/encore-core-preflight.yml").read_text()
for path in ("tools/check-maintained-a64-interface.py",
             "tools/check-native-a64-cache-invalidation-host.py",
             "tools/verify/hle/check-hle-overlay-layout.py",
             "tools/check-native-hle-suspend-noop-host.py",
             "tools/install-active-core-backports.py"):
    assert "python3 -B "+path in preflight,path
assert "python3 -B tools/ci/check-final-engine-owner-contracts.py" in preflight
print("ENCORE_FINAL_ENGINE_OWNERS_PASS standard_JIT=1 host_SM_lock_safe=1 context_permit=1 source_hashes=3")
