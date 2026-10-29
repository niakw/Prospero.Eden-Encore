#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile actual sparse range lookup/decommit under concurrent range reuse.

The range's non-atomic end/owned metadata is protected by sparse_mutex.
Decommit must not scan the table before acquiring that mutex. Also verify
real host page zeroing, read-only remap and dense fallback.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/memory_pages.cpp").read_text()
lookup_anchor = "SparseRange* SparseRangeOf(std::uintptr_t address) {"
lookup_end = "\n#ifdef PS5_NATIVE\nstd::int64_t zero_block"
decommit_anchor = "void DecommitSparsePage(std::uintptr_t page) noexcept {"
decommit_end = "\n// Address space the sparse tables span"
assert source.count(lookup_anchor) == 1
assert source.count(decommit_anchor) == 1
lookup = lookup_anchor + source.split(lookup_anchor, 1)[1].split(lookup_end, 1)[0]
decommit = decommit_anchor + source.split(decommit_anchor, 1)[1].split(decommit_end, 1)[0]
assert decommit.count("SparseRangeOf(page)") == 1, "avoid the unlocked duplicate 64-slot scan"
assert decommit.index("const std::lock_guard lock{sparse_mutex};") < decommit.index(
    "SparseRangeOf(page)"), "range.end and range.owned must be read under sparse_mutex"
assert "range->owned[slot].store(false, std::memory_order_release);" in decommit
assert "sparse_committed.fetch_sub(SparseSlot, std::memory_order_relaxed);" in decommit
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"

prefix = r'''
#include <array>
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>
#include <sys/mman.h>
#include <unistd.h>
const std::size_t SparseSlot = static_cast<std::size_t>(sysconf(_SC_PAGESIZE));
struct SparseRange {
    std::atomic<std::uintptr_t> begin{0};
    std::uintptr_t end = 0;
    std::atomic<bool>* owned = nullptr;
    std::int64_t* physical = nullptr;
};
std::array<SparseRange, 64> sparse_ranges{};
std::mutex sparse_mutex;
std::atomic<std::size_t> sparse_committed{0};
'''
suffix = r'''
int main() {
    auto* p = static_cast<unsigned char*>(mmap(nullptr, 2 * SparseSlot,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    auto* dense = static_cast<unsigned char*>(mmap(nullptr, SparseSlot,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    assert(p != MAP_FAILED && dense != MAP_FAILED);
    std::memset(p, 0xAB, 2 * SparseSlot);
    std::memset(dense, 0xCD, SparseSlot);
    std::atomic<bool> owned[2];
    owned[0].store(true); owned[1].store(true);
    std::int64_t physical[2]{0, 0};
    auto& range = sparse_ranges[0];
    range.owned = owned;
    range.physical = physical;
    range.end = reinterpret_cast<std::uintptr_t>(p) + 2 * SparseSlot;
    range.begin.store(reinterpret_cast<std::uintptr_t>(p), std::memory_order_release);
    sparse_committed.store(2 * SparseSlot);
    DecommitSparsePage(reinterpret_cast<std::uintptr_t>(p));
    assert(!owned[0].load() && owned[1].load());
    assert(sparse_committed.load() == SparseSlot);
    for (std::size_t i = 0; i < SparseSlot; ++i) assert(p[i] == 0);
    DecommitSparsePage(reinterpret_cast<std::uintptr_t>(p)); // idempotent
    assert(sparse_committed.load() == SparseSlot);
    DecommitSparsePage(reinterpret_cast<std::uintptr_t>(p + SparseSlot));
    assert(!owned[1].load() && sparse_committed.load() == 0);
    for (std::size_t i = 0; i < SparseSlot; ++i) assert(p[SparseSlot + i] == 0);
    DecommitSparsePage(reinterpret_cast<std::uintptr_t>(dense)); // dense fallback
    assert(dense[0] == 0xCD && dense[SparseSlot - 1] == 0xCD);

    // Reuse the range slot while a dense lookup repeatedly scans it.
    // Writers and the source-extracted Decommit both use sparse_mutex.
    std::thread writer([&] {
        for (int i = 0; i < 4096; ++i) {
            std::lock_guard lock{sparse_mutex};
            range.begin.store(0, std::memory_order_release);
            range.end = reinterpret_cast<std::uintptr_t>(p) + 2 * SparseSlot;
            range.begin.store(reinterpret_cast<std::uintptr_t>(p), std::memory_order_release);
        }
    });
    for (int i = 0; i < 4096; ++i)
        DecommitSparsePage(reinterpret_cast<std::uintptr_t>(dense));
    writer.join();
    assert(sparse_committed.load() == 0);
    assert(munmap(p, 2 * SparseSlot) == 0);
    assert(munmap(dense, SparseSlot) == 0);
}
'''
with tempfile.TemporaryDirectory(prefix="eden-sparse-decommit-") as tmp:
    path = Path(tmp) / "sparse-decommit.cpp"
    binary = Path(tmp) / "sparse-decommit"
    path.write_text(prefix + lookup + "\n" + decommit + "\n" + suffix)
    for optimization in ("-O0", "-O2"):
        subprocess.run([compiler, "-std=c++20", optimization, "-pthread", "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(path), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
print("SPARSE_DECOMMIT_LOCK_PASS: source-extracted O0/O2 UBSan, single scan under lock, page reuse")
