#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source and host contracts for the paired upstream guest scheduler locks.

The source tree is based on a pinned upstream archive: replacing only
k_thread.h, k_slab_heap.h, and k_scheduler.cpp is intentional. The paired slab override stays version-pinned (including its mutex-contained relaxed atomics); Encore uses a cross-host-worker
binary semaphore for the guest context handoff, replacing owner-bound mutex.
This is not a runtime FPS or title-deadlock qualification.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
rel = "vendor/encore-active/eden-threading/src/core/hle/kernel"
directory = root / rel
expected_hashes = {
    "k_thread.h": "git:e2f359a54cb6b879bdd41f092cf1ea19fb03e4e6",
    "k_slab_heap.h": "git:307b8ff131df472cbca0e6eed27d9d142821b8b7",
    "k_scheduler.cpp": "git:6bf49c0165ecac602628679adbb8cee8d8407190",
}
sources = {}
for name, expected_sha in expected_hashes.items():
    path = directory / name
    assert path.exists(), f"Missing vendored file {path}"
    data = path.read_bytes()
    # Audited modified overlays use exact Git blobs; legacy SHA256 entries remain supported.
    digest = (hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
              if expected_sha.startswith("git:") else hashlib.sha256(data).hexdigest())
    assert digest == expected_sha.removeprefix("git:"), f"Requalify changed {name}"
    sources[name] = data.decode("utf-8")

thread = sources["k_thread.h"]
slab = sources["k_slab_heap.h"]
scheduler = sources["k_scheduler.cpp"]
assert "#include \"common/spin_lock.h\"" not in thread + slab
assert "Common::SpinLock m_context_guard" not in thread
assert "Common::SpinLock m_lock" not in slab
assert "#include <semaphore>" in thread
assert "std::binary_semaphore m_context_guard{1};" in thread
assert "std::mutex m_context_guard" not in thread
assert "std::mutex m_lock;" in slab
assert "Node* ret = m_head.load(std::memory_order_relaxed);" in slab
assert "m_head.store(ret->next, std::memory_order_relaxed);" in slab
assert "node->next = m_head.load(std::memory_order_relaxed);" in slab
assert "m_head.store(node, std::memory_order_relaxed);" in slab
assert "std::destroy_at(obj);" in slab
assert slab.index("std::destroy_at(obj);") < slab.index("BaseHeap::Free(obj);")
assert "KSlabHeapImpl() = default;" in slab
assert "constexpr KSlabHeapImpl()" not in slab
assert "#include <mutex>" in slab

def section(begin: str, end: str) -> str:
    assert scheduler.count(begin) == 1
    return scheduler.split(begin, 1)[1].split(end, 1)[0]

retry = section(
    "if (m_state.needs_scheduling.load(std::memory_order_seq_cst)) {\n"
    "            // On retry,",
    "goto retry;")
unload = section("void KScheduler::Unload(", "void KScheduler::Reload(")
assert "while (!highest_priority_thread->m_context_guard.try_acquire())" in scheduler
assert retry.count("highest_priority_thread->m_context_guard.release()") == 1
assert unload.count("thread->m_context_guard.release()") == 1
assert "m_context_guard.try_lock()" not in scheduler
assert "m_context_guard.unlock()" not in scheduler
assert "m_context_guard.try_acquire()" not in retry + unload
assert "DEBUG_ASSERT(!can_lock)" not in retry + unload

cmake = (root / "headless/CMakeLists.txt").read_text()
module = (root / "vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
native = (root / ".github/workflows/build-040-zbic.yml").read_text()

assert "option(EDEN_BLOCKING_GUEST_CONTEXT_LOCKS" in cmake
assert "native-hle-overrides.cmake" in cmake
assert "if(EDEN_BLOCKING_GUEST_CONTEXT_LOCKS)" in module
assert "k_thread.h k_slab_heap.h k_scheduler.cpp" in module
assert "target_include_directories(core BEFORE PUBLIC" in module
assert "encore_replace_core_source(" in module
assert 'file(REMOVE "${PORT_BUILD_DIR}/include/core/hle/kernel/k_slab_heap.h")' in cmake
for name in expected_hashes:
    assert name in module
for target in ("core", "video_core", "audio_core", "hid_core", "network",
               "input_common", "frontend_common", "shader_recompiler", "dynarmic"):
    assert target in module
for yml in (workflow, native):
    assert "tools/check-upstream-guest-scheduler-locks.py" in yml

# The separate HLE CMake smoke configures all four source-selection variants.
# This test owns only upstream hashes and actual lazy-mutex host semantics.
assert "python3 -B tools/verify/hle/check-hle-cmake-select-host.py" in workflow

# Cross-host-worker release is legal for std::binary_semaphore, not std::mutex.
# Compile the actual maintained member type and release sites in a finite
# two-worker interleaving. No emulator or console is run.
fixture = r"""
#include <cassert>
#include <cstdio>
#include <semaphore>
#include <thread>
struct KThread {
    std::binary_semaphore m_context_guard{1};
};
static void retry_failed_switch(KThread* highest_priority_thread) {
    highest_priority_thread->m_context_guard.release();
}
static void unload_thread(KThread* thread) {
    thread->m_context_guard.release();
}
int main() {
    for (int trial=0; trial<256; ++trial) {
        KThread guest;
        std::binary_semaphore ready{0};
        std::thread worker_acquire([&] {
            assert(guest.m_context_guard.try_acquire());
            assert(!guest.m_context_guard.try_acquire());
            ready.release();
        });
        std::thread worker_release([&] {
            ready.acquire();
            unload_thread(&guest);
        });
        worker_acquire.join();
        worker_release.join();
        assert(guest.m_context_guard.try_acquire());
        retry_failed_switch(&guest);
        assert(guest.m_context_guard.try_acquire());
        guest.m_context_guard.release();
    }
    std::puts("PASS cross-worker context semaphore acquire/release/retry");
}
"""
assert "std::binary_semaphore m_context_guard{1};" in fixture
for literal in ("highest_priority_thread->m_context_guard.release();",
                "thread->m_context_guard.release();"):
    assert literal in scheduler and literal in fixture
compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
assert compiler, "C++20 host compiler required"
env = os.environ.copy()
if sys.platform == "darwin" and not env.get("SDKROOT"):
    sdk = Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk")
    if sdk.is_dir():
        env["SDKROOT"] = str(sdk)
with tempfile.TemporaryDirectory(prefix="encore-scheduler-handoff-") as folder:
    cpp = Path(folder) / "handoff.cpp"
    exe = Path(folder) / "handoff"
    cpp.write_text(fixture)
    subprocess.run([compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                    "-pthread", str(cpp), "-o", str(exe)], check=True, env=env, timeout=60)
    subprocess.run([str(exe)], check=True, env=env, timeout=15)

print("PASS maintained guest-context semaphore + requalified slab mutex atomics + CMake selection")
print("HOST ONLY: native build and guest gameplay still require qualification")
