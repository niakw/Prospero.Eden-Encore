#!/usr/bin/env python3
"""Deterministic host-only witness for the unclosed tracked-page/JIT handoff.

A deliberately paused checked-access guard stores after GPU tracking begins
without a callback. A separate run-level quiescence MODEL closes that specific
schedule. Neither witness qualifies native performance, reentrancy, lifetime,
the actual Dynarmic emitter, or GPU device fences. Native #187 stays OFF.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
read = lambda path: (root / path).read_text()
checked = read("vendor/encore-active/eden-core/src/dynarmic/backend/x64/emit_x64_memory.h")
host = read("src/host_memory.cpp")
memory = read("vendor/sources/eden/src/core/memory.cpp")
page = read("vendor/sources/eden/src/common/page_table.h")
jit_test = read("headless/memory_check.cpp")
replay = read("headless/gpu_deferred_replay.h")
workflow = read(".github/workflows/encore-core-preflight.yml")

# Fail closed if any source contract of the negative witness changes.
assert "code.test(code.byte[r13 + index - checked_map_bytes], blocked_bit);" in checked
assert "std::fill(page_access.begin() + first, page_access.begin() + last + 1, access);" in host
assert "Refresh(first, last);" in host
assert "return raw.marked && !ignore_marked ? 0" in page
mark = memory.split("void RasterizerMarkRegionCached(", 1)[1].split("\n    /**", 1)[0]
assert mark.index("host_buffer->Protect(vaddr, size, perm);") < mark.index(
    "entry.MarkRasterizerCached();")
assert "GuestStoreOrderGate" not in mark
assert "static void StressFastmemA32()" in jit_test
assert "inline constexpr bool kNativePostStorePublicationReady = false;" in replay
assert "python3 -B tools/check-native-tracked-page-handoff-host.py" in workflow

cpp = r"""
#include <atomic>
#include <cassert>
#include <cstdio>
#include <mutex>
#include <semaphore>
#include <shared_mutex>
#include <thread>
struct Page {
    std::atomic<bool> writable{true};
    std::atomic<bool> tracked{false};
    std::atomic<int> ram{0};
    std::atomic<int> callbacks{0};
    std::atomic<int> first_gpu_view{-1};
};
void UnclosedTransition() {
    Page p;
    std::binary_semaphore checked{0}, release_store{0};
    std::thread jit([&] {
        const bool direct = p.writable.load(std::memory_order_acquire);
        assert(direct);
        checked.release();
        release_store.acquire();
        if (direct) p.ram.store(7, std::memory_order_release);
        else p.callbacks.fetch_add(1, std::memory_order_relaxed);
    });
    checked.acquire();
    // Native sequence protects checked fastmem before marking the PTE.
    p.writable.store(false, std::memory_order_release);
    p.tracked.store(true, std::memory_order_release);
    p.first_gpu_view.store(p.ram.load(std::memory_order_acquire));
    release_store.release();
    jit.join();
    assert(p.first_gpu_view == 0 && p.ram == 7 && p.callbacks == 0);
    std::puts("TRACKED_HANDOFF_NEGATIVE_STALE_GUARD_REPRODUCED");
}
void RunQuiescenceModelOnly() {
    Page p;
    std::shared_mutex run_gate;
    std::binary_semaphore checked{0}, release_store{0};
    std::atomic<bool> transition_requested{false};
    std::thread jit([&] {
        // Run-level lease: NOT PRESENT in native CPU/JIT implementation.
        std::shared_lock lease(run_gate);
        const bool direct = p.writable.load(std::memory_order_acquire);
        assert(direct);
        checked.release();
        release_store.acquire();
        if (direct) p.ram.store(7, std::memory_order_release);
    });
    checked.acquire();
    std::thread gpu([&] {
        transition_requested.store(true, std::memory_order_release);
        std::unique_lock transition(run_gate);
        p.writable.store(false, std::memory_order_release);
        p.tracked.store(true, std::memory_order_release);
        p.first_gpu_view.store(p.ram.load(std::memory_order_acquire));
    });
    while (!transition_requested.load(std::memory_order_acquire))
        std::this_thread::yield();
    assert(!p.tracked.load(std::memory_order_acquire));
    release_store.release();
    jit.join();
    gpu.join();
    assert(p.tracked && !p.writable && p.ram == 7 && p.first_gpu_view == 7);
    std::thread next([&] {
        std::shared_lock lease(run_gate);
        if (!p.writable.load(std::memory_order_acquire))
            p.callbacks.fetch_add(1, std::memory_order_relaxed);
        else p.ram.store(9, std::memory_order_release);
    });
    next.join();
    assert(p.callbacks == 1 && p.ram == 7);
    std::puts("TRACKED_HANDOFF_RUN_QUIESCENCE_MODELED_ONLY");
}
int main() {
    UnclosedTransition();
    RunQuiescenceModelOnly();
    std::puts("TRACKED_HANDOFF_NATIVE_UNQUALIFIED_GATE_CLOSED");
}
"""
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler, "C++20 compiler required for host-only interleaving witness"
with tempfile.TemporaryDirectory(prefix="encore-tracked-handoff-") as tmp:
    source = Path(tmp) / "handoff.cpp"
    binary = Path(tmp) / "handoff"
    source.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra",
                    "-Werror", "-pthread", str(source), "-o", str(binary)],
                   check=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True,
                            text=True, timeout=15)
    print(result.stdout, end="")
