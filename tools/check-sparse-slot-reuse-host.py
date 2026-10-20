#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile and execute the actual Encore-maintained sparse decommit code on a host.

One 2 MiB slot backs 128 host pages of 16 KiB each. Clearing a page with
another still mapped must erase its contents, even without releasing the slot.
This is a host memory test, NOT a PS5 gameplay or GPU qualification.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
sparse = (root / "vendor/encore-active/eden-core/src/common/sparse_large_vector.h").read_text()
anchor = "    void DecommitPage(std::size_t index) noexcept {"
assert sparse.count(anchor) == 1
method = anchor + sparse.split(anchor, 1)[1].split(
    "    void CommitPage(std::size_t index) noexcept {", 1)[0]
assert method.startswith(anchor)
assert "std::memset(reinterpret_cast<void*>(page_address), 0, HostPageSize);" in method
assert "for (std::size_t word = first_page >> 6; word <= last_word; ++word)" in method
assert "u64 bits = committed_pages[word].load(std::memory_order_acquire);" in method
compiler = (shutil.which("clang++-18") or shutil.which("clang++") or
            shutil.which("g++"))
assert compiler, "A host C++20 compiler is required"

prefix = r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <vector>
using u64 = std::uint64_t;
constexpr std::size_t HostPageSize = 16384;
constexpr std::size_t HostPageBits = 14;
constexpr std::uintptr_t HostPageMask = ~(std::uintptr_t(HostPageSize) - 1);
constexpr std::size_t Slot = 2 * 1024 * 1024;
static unsigned releases = 0;
static unsigned bitmap_reads = 0;
struct TrackedAtomic {
    std::atomic<u64> state{};
    u64 load(std::memory_order order) const noexcept {
        ++bitmap_reads;
        return state.load(order);
    }
    u64 fetch_or(u64 bits, std::memory_order order) noexcept {
        return state.fetch_or(bits, order);
    }
    u64 fetch_and(u64 bits, std::memory_order order) noexcept {
        return state.fetch_and(bits, order);
    }
    void store(u64 bits, std::memory_order order) noexcept {
        state.store(bits, order);
    }
};
static bool dense = false;
std::size_t SparseCommitSpan() noexcept { return Slot; }
void DecommitSparsePage(std::uintptr_t p) noexcept {
    if (dense) return;
    ++releases;
    std::memset(reinterpret_cast<void*>(p), 0, Slot);
}
struct Table {
    using T = u64;
    u64* base_ptr;
    std::size_t alloc_size;
    std::vector<TrackedAtomic> committed_pages;
    Table(void* p, std::size_t bytes = Slot)
      : base_ptr(static_cast<u64*>(p)), alloc_size(bytes),
        committed_pages(Slot / HostPageSize / 64) {
        for (auto& bit : committed_pages)
            bit.store(0, std::memory_order_relaxed);
    }
    void mark(std::size_t host_page) {
        committed_pages[host_page >> 6].fetch_or(
            u64(1) << (host_page & 63), std::memory_order_relaxed);
    }
"""
suffix = r"""
};
int main() {
    auto* raw = static_cast<unsigned char*>(std::aligned_alloc(Slot, Slot));
    assert(raw);
    std::memset(raw, 0, Slot);
    constexpr auto second = HostPageSize / sizeof(u64);
    {
        Table t(raw);
        t.mark(0);
        t.mark(1);
        std::memset(raw, 0xA5, HostPageSize);
        std::memset(raw + HostPageSize, 0x5A, HostPageSize);
        t.DecommitPage(0);
        assert(releases == 0);
        for (std::size_t i = 0; i < HostPageSize; ++i) {
            assert(raw[i] == 0);
            assert(raw[HostPageSize + i] == 0x5A);
        }
        t.mark(0);              // reused page: no stale bytes
        t.DecommitPage(second); // page zero still retains the slot
        assert(releases == 0);
        t.DecommitPage(0);      // last mapped host page
        assert(releases == 1);
    }
    {
        // Keep the last slot page occupied. The original loop reloaded its
        // two bitmap words up to 128 times. The new scan loads at most twice.
        Table t(raw);
        constexpr auto last_page_index = Slot / HostPageSize - 1;
        t.mark(0);
        t.mark(last_page_index);
        bitmap_reads = 0;
        t.DecommitPage(0);
        assert(releases == 1 && bitmap_reads <= 2);
        bitmap_reads = 0;
        t.DecommitPage(last_page_index * (HostPageSize / sizeof(u64)));
        assert(releases == 2 && bitmap_reads <= 2);
    }
    {
        // Partial last bitmap word must mask bits outside the table.
        Table t(raw, HostPageSize + 4);
        t.mark(0);
        t.mark(1);
        bitmap_reads = 0;
        t.DecommitPage(0);
        assert(releases == 2 && bitmap_reads <= 1);
        t.DecommitPage(second);
        assert(releases == 3);
    }
    dense = true;                // fallback never releases the slot
    std::memset(raw, 0xCE, HostPageSize);
    {
        Table t(raw);
        t.mark(0);
        t.DecommitPage(0);
        assert(releases == 3);
        for (std::size_t i = 0; i < HostPageSize; ++i)
            assert(raw[i] == 0);
    }
    std::free(raw);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-sparse-reuse-") as td:
    path = Path(td) / "sparse.cpp"
    program = Path(td) / "sparse"
    path.write_text(prefix + method + suffix)
    subprocess.run([compiler, "-std=c++20", "-O1", "-Wall", "-Wextra",
                    "-Werror", str(path), "-o", str(program)], check=True)
    subprocess.run([str(program)], check=True)
print("PASS: host C++ sparse table word scan, partial-slot masks and dense fallback")
