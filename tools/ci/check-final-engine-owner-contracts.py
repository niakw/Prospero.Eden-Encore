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
 # J10 was a "reviewed without edit" historical source. The JIT drain
 # is now a source correction; retain the old hash below as provenance and
 # pin the new reviewed source with the source-extracted reentrant witness.
 "jit": "aaff079cedf068b1d032af6cb3abc5f8b5e72178",
}
def gitblob(data: bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
# Historical pre-pressure-rollback source: 26ae49088a528c4cf27712f639948604de2260d4.
# Reviewed delta at new SHA: the two unprotected invalidate_entire_cache=true
# writes on low JIT code-space and bad_alloc now use ClearCache(), which
# publishes under invalidation_mutex. The source-extracted host witness
# checks both paths and reentrant guest requests.
JIT_PREVIOUS_REVIEW_BLOB = "20362a046adfe89d65225c1822104f2910eeb2c5"
assert expected["jit"] != JIT_PREVIOUS_REVIEW_BLOB
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
                  "emitter.InvalidateCacheRanges(ranges);",
                  "ranges.swap(invalid_cache_ranges);",
                  "clear_all = invalidate_entire_cache;",
                  "invalidate_entire_cache = false;",
                  "if (length - 1 > (~u64{0} - start_address))"):
    assert invariant in jit,invariant
assert jit.index("ranges.swap(invalid_cache_ranges);") < jit.index("emitter.InvalidateCacheRanges(ranges);")
assert jit.count("Publish the full-clear request under invalidation_mutex;") == 2
assert "emitter.InvalidateCacheRanges(invalid_cache_ranges);" not in jit
# Reviewed source must be tied to a HOST proof, not just a new opaque digest.
proof = (root/"tools/check-native-jit-invalidation-snapshot-host.py").read_text()
assert "PerformRequestedCacheInvalidation" in proof
assert "invalid_cache_ranges" in proof and "p.InvalidateCacheRange(" in proof
cmake=(root/"headless/CMakeLists.txt").read_text()
for invariant in ("a64_interface_standard.cpp", "a64_interface_shared.cpp",
                  'NOT EDEN_BLOCKING_GUEST_CONTEXT_LOCKS',
                  'EDEN_JIT_A64_BATCH=1', 'EDEN_JIT_A64_DEV_PROFILE=1',
                  'NOT EDEN_A32_FASTMEM'):
    assert invariant in cmake,invariant
preflight=(root/".github/workflows/encore-core-preflight.yml").read_text()
for path in ("tools/check-maintained-a64-interface.py",
             "tools/check-native-a64-cache-invalidation-host.py",
             "tools/check-native-jit-invalidation-snapshot-host.py",
             "tools/verify/hle/check-hle-overlay-layout.py",
             "tools/check-native-hle-suspend-noop-host.py",
             "tools/install-active-core-backports.py"):
    assert "python3 -B "+path in preflight,path
assert "python3 -B tools/ci/check-final-engine-owner-contracts.py" in preflight
print("ENCORE_FINAL_ENGINE_OWNERS_PASS standard_JIT=1 host_SM_lock_safe=1 context_permit=1 source_hashes=3 jit_fix_witness=1")
