#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile and execute the actual derived PS5 sparse decommit code on a host.

One 2 MiB slot backs 128 host pages of 16 KiB each. Clearing a page with
another still mapped must erase its contents, even without releasing the slot.
This is a host memory test, NOT a PS5 gameplay or GPU qualification.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/CMakeLists.txt").read_text()
anchor = "set(sparse_private_replacement [=["
assert cmake.count(anchor) == 1
body = cmake.split(anchor, 1)[1].split("]=])", 1)[0]
method = body.split("    void CommitPage(std::size_t index) noexcept {", 1)[0]
assert method.startswith("    void DecommitPage(std::size_t index) noexcept {")
assert "std::memset(reinterpret_cast<void*>(page_address), 0, HostPageSize);" in method
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
constexpr std::uintptr_t HostPageMask = ~(std::uintptr_t(HostPageSize) - 1);
constexpr std::size_t Slot = 2 * 1024 * 1024;
static unsigned releases = 0;
static bool dense = false;
std::size_t SparseCommitSpan() noexcept { return Slot; }
void DecommitSparsePage(std::uintptr_t p) noexcept {
    if (dense) return;
    ++releases;
    std::memset(reinterpret_cast<void*>(p), 0, Slot);
}
struct Table {
    u64* base_ptr;
    std::size_t alloc_size;
    std::vector<std::atomic<u64>> committed_pages;
    Table(void* p)
      : base_ptr(static_cast<u64*>(p)), alloc_size(Slot),
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
    dense = true;                // fallback never releases the slot
    std::memset(raw, 0xCE, HostPageSize);
    {
        Table t(raw);
        t.mark(0);
        t.DecommitPage(0);
        assert(releases == 1);
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
print("PASS: host C++ sparse table page clearing, 2-MiB release and dense fallback")
