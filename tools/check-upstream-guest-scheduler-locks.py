#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source and host contracts for the paired upstream guest scheduler locks.

The source tree is based on a pinned upstream archive: replacing only
k_thread.h, k_slab_heap.h, and k_scheduler.cpp is intentional. Both upstream
changes are inseparable; an isolated lazy-mutex workaround on SpinLock is wrong.
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
    "k_thread.h": "dafd67c04e9e25fbaf096536fbce0eef3162ef3c046391ff45f138057947b808",
    "k_slab_heap.h": "13bdea0823a9bb916cbc6b26c4c1d225a187125b365b35e68747f73658e0fc1e",
    "k_scheduler.cpp": "585b84722c6fdc717e0c6d54c5d74af45f2b7da6f482a517642efb8c89399750",
}
sources = {}
for name, expected_sha in expected_hashes.items():
    path = directory / name
    assert path.exists(), f"Missing vendored file {path}"
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected_sha, f"Requalify changed {name}"
    sources[name] = data.decode("utf-8")

thread = sources["k_thread.h"]
slab = sources["k_slab_heap.h"]
scheduler = sources["k_scheduler.cpp"]
assert "#include \"common/spin_lock.h\"" not in thread + slab
assert "Common::SpinLock m_context_guard" not in thread
assert "Common::SpinLock m_lock" not in slab
assert "std::mutex m_context_guard{};" in thread
assert "std::mutex m_lock;" in slab
assert "KSlabHeapImpl() = default;" in slab
assert "constexpr KSlabHeapImpl()" not in slab
assert "#include <mutex>" in slab

def section(begin: str, end: str) -> str:
    assert scheduler.count(begin) == 1
    return scheduler.split(begin, 1)[1].split(end, 1)[0]

retry = section(
    "if (m_state.needs_scheduling.load(std::memory_order_seq_cst)) {\n"
    "            // libc++",
    "goto retry;")
unload = section("void KScheduler::Unload(", "void KScheduler::Reload(")
assert retry.count("highest_priority_thread->m_context_guard.try_lock()") == 1
assert retry.count("DEBUG_ASSERT(!can_lock)") == 1
assert retry.index("m_context_guard.try_lock()") < retry.index("m_context_guard.unlock()")
assert unload.count("thread->m_context_guard.try_lock()") == 1
assert unload.count("DEBUG_ASSERT(!can_lock)") == 1
assert unload.index("m_context_guard.try_lock()") < unload.index("m_context_guard.unlock()")

cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
native = (root / ".github/workflows/build-040-zbic.yml").read_text()
assert "option(EDEN_BLOCKING_GUEST_CONTEXT_LOCKS" in cmake
assert "if(EDEN_BLOCKING_GUEST_CONTEXT_LOCKS)" in cmake
assert "eden_pinned_scheduler_idx EQUAL -1" in cmake
assert 'target_include_directories(core BEFORE PUBLIC "${EDEN_THREAD_ROOT}")' in cmake
assert 'list(REMOVE_ITEM eden_kernel_sources "hle/kernel/k_scheduler.cpp")' in cmake
assert 'set_property(TARGET core PROPERTY SOURCES "${eden_kernel_sources}")' in cmake
for name in expected_hashes:
    assert name in cmake
for target in ("core", "video_core", "audio_core", "hid_core", "network",
               "input_common", "frontend_common", "shader_recompiler", "dynarmic"):
    assert target in cmake
for yml in (workflow, native):
    assert "tools/check-upstream-guest-scheduler-locks.py" in yml

# A deliberately lazy host mutex: unlike a normal std::mutex, unlock before
# the first try_lock is invalid. These two paths represent the exact upstream
# guards asserted above. They DO NOT imitate guest thread scheduling.
fixture = r"""
#include <cassert>
#include <cstdio>
struct LazyContext {
    bool initialized = false;
    bool held = true;
    bool try_lock() {
        initialized = true;
        return !held;
    }
    void unlock() {
        assert(initialized && held);
        held = false;
    }
};
static void retry_after_failed_switch(LazyContext& guard) {
    [[maybe_unused]] auto const can_lock = guard.try_lock();
    assert(!can_lock);
    guard.unlock();
}
static void unload_nonterminated_thread(LazyContext& guard) {
    [[maybe_unused]] auto const can_lock = guard.try_lock();
    assert(!can_lock);
    guard.unlock();
}
int main() {
    LazyContext retry{};
    retry_after_failed_switch(retry);
    assert(retry.initialized && !retry.held);
    LazyContext unload{};
    unload_nonterminated_thread(unload);
    assert(unload.initialized && !unload.held);
    std::puts("PASS paired lazy-mutex retry and unload contracts");
}
"""
compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
assert compiler, "C++20 host compiler required"
env = os.environ.copy()
if sys.platform == "darwin" and not env.get("SDKROOT"):
    sdk = Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk")
    if sdk.is_dir():
        env["SDKROOT"] = str(sdk)
with tempfile.TemporaryDirectory(prefix="encore-scheduler-guard-") as folder:
    cpp = Path(folder) / "lazy.cpp"
    exe = Path(folder) / "lazy"
    cpp.write_text(fixture)
    subprocess.run([compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                    str(cpp), "-o", str(exe)], check=True, env=env, timeout=60)
    subprocess.run([str(exe)], check=True, env=env, timeout=15)
print("PASS paired upstream kernel source overlays + exact hashes + CMake/CI wiring")
print("HOST ONLY: native build and guest gameplay still require qualification")
