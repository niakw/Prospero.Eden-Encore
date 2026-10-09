#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile the real dev PcSignal handler with synthetic host register contexts.

Tests signal-handler ring wrap; no PS5 firmware, kernel signals, native
compilation, or actual concurrent guest execution is represented.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
perf = (root / "headless/performance.cpp").read_text()
start = perf.index("void PcSignal(int, siginfo_t*, void* context) {")
end = perf.index("\n}\n#endif\n#ifdef PS5_NATIVE", start) + 2
handler = perf[start:end]
assert "sampled_pcs[slot].store(" in handler
assert "sampled_core_pcs[core_index % sampled_core_pcs.size()].store(" in handler
assert "pc_count.store(index + 1, std::memory_order_release);" in handler
assert "core_pc_count.store(core_index + 1, std::memory_order_release);" in handler
assert "#if defined(EDEN_DEV_WAIT_CALLERS) && defined(PS5_NATIVE)" in handler
assert "if (index >= sampled_pcs.size()) return;" in handler

compiler = next((name for name in ("clang++-18", "clang++", "g++") if shutil.which(name)), None)
if not compiler:
    raise SystemExit("C++20 compiler required for actual PC handler ring smoke")

prefix = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <csignal>
#include <cstdint>
#include <pthread.h>
namespace Eden::Performance {
namespace {
static_assert(std::atomic<uintptr_t>::is_always_lock_free);
std::array<std::atomic<uintptr_t>, 8192> sampled_pcs{};
std::atomic<unsigned> pc_count{};
std::array<std::atomic<uintptr_t>, 65536> sampled_core_pcs{};
std::atomic<unsigned> core_pc_count{};
pthread_t core_sample_thread{};
std::atomic<bool> core_sample_ready{};
"""
suffix = r"""
} // anonymous namespace
} // Eden::Performance

int main() {
    using namespace Eden::Performance;
    std::array<uintptr_t, 32> registers{};
    for (unsigned i = 0; i < 10000; ++i) {
        registers[224 / sizeof(uintptr_t)] = i + 1;
        PcSignal(0, nullptr, registers.data());
    }
    assert(pc_count.load(std::memory_order_acquire) == 10000);
    for (unsigned i = 10000 - sampled_pcs.size(); i < 10000; ++i)
        assert(sampled_pcs[i % sampled_pcs.size()].load() == i + 1);
    core_sample_thread = pthread_self();
    core_sample_ready.store(true, std::memory_order_release);
    for (unsigned i = 0; i < 90000; ++i) {
        registers[224 / sizeof(uintptr_t)] = 0x100000 + i;
        PcSignal(0, nullptr, registers.data());
    }
    assert(core_pc_count.load(std::memory_order_acquire) == 90000);
    assert(pc_count.load(std::memory_order_acquire) == 10000);
    for (unsigned i = 90000 - sampled_core_pcs.size(); i < 90000; ++i)
        assert(sampled_core_pcs[i % sampled_core_pcs.size()].load() == 0x100000 + i);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-pc-ring-") as folder:
    folder = Path(folder)
    src, exe = folder / "sample.cpp", folder / "sample"
    src.write_text(prefix + handler + suffix)
    subprocess.run([compiler, "-std=c++20", "-O2", "-pthread", "-Wall", "-Wextra",
                    "-Werror", str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("PASS: source-extracted PcSignal PC-only ring wraps GPU/guest atomics across 10k/90k events")
print("No PS5 signals, SDK, firmware, running FC27, or linked native binary validated")
