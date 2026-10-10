#!/usr/bin/env python3
"""Enforce accurate PS5 installed-vs-direct-vs-app-owned memory reporting.

Compile the actual pure accounting header under ASan/UBSan. This is a
host-side source and arithmetic contract, NOT native PS5 evidence that
all 16 GiB installed GDDR6 is available to the application.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "headless/direct_pool_accounting.h").read_text()
perf = (root / "headless/performance.cpp").read_text()
heap = (root / "headless/heap_arenas.inc").read_text()
pages = (root / "src/memory_pages.cpp").read_text()
bridge = (root / "headless/heap_pages.cpp").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
for token in (
    '#include "direct_pool_accounting.h"',
    '::Common::SparseUsage(&sparse_virtual, &sparse_physical);',
    '::Common::SparseJitUsage(&jit_reserved, &jit_committed);',
    '::Common::DenseJitDirectBytes()',
    '::Eden::DirectPool::Summarize(total, {',
    'EDEN_DIRECT_POOL_OWNERS phase=%s extent=%llu heap_roots=%zu',
    'unclassified=%llu tracked_within_extent=%u',
    'largest_free_known=%u largest_free=%zu',
    '.heap_large = heap_large_physical,',
    'large_owner_known=%u',
):
    assert token in perf, f"Missing physical pool provenance: {token}"
assert "SaturatingAdd" in header
assert "std::numeric_limits<std::uint64_t>::max()" in header
assert "return {extent, used, 0, true, false};" in header
assert "return {extent, used, extent - used, true, true};" in header
assert "untracked is not free" in perf.lower(), "Do not present unclassified as free"
assert 'heap_large_requested=%zu' in perf
assert 'eden_heap_large_physical_held' in heap
assert 'atomic_fetch_add_explicit(&eden_heap_large_physical_bytes, physical_bytes' in heap
assert 'atomic_fetch_sub_explicit(&eden_heap_large_physical_bytes,' in heap
assert 'eden_heap_pages_physical_size(block)' in heap
assert 'AllocatedMemoryPagesSpan(const void* pointer)' in pages
assert 'header_of(pointer, static_cast<std::size_t>(page)).total' in pages
assert 'Common::AllocatedMemoryPagesSpan(base)' in bridge
assert 'size_t eden_heap_pages_physical_size(void *);' in cmake
assert perf.index("void ReportDirectMemoryState(") < perf.index("EDEN_DIRECT_POOL_OWNERS")
assert perf.index("EDEN_DIRECT_POOL_OWNERS") < perf.index("void ReportGpuThread(")
compiler = next((name for name in ("clang++-18", "clang++", "g++")
                 if shutil.which(name)), None)
if compiler is None:
    raise SystemExit("No C++20 compiler for direct pool ledger source check")
code = r"""
#include <cassert>
#include <cstdint>
#include <limits>
#include "direct_pool_accounting.h"
int main() {
    using namespace Eden::DirectPool;
    constexpr std::uint64_t MiB = 1024ULL * 1024;
    constexpr std::uint64_t GiB = 1024ULL * MiB;
    // 16 GiB physically installed in PS5 is NOT what firmware gives Encore.
    // Old real FW 13.60 console directly exposed 12 GiB, and its Encore
    // heap committed 1280 MiB after game exit. Not Sony OS-reserved memory.
    constexpr auto old = Summarize(12*GiB, {.heap_roots=1280*MiB});
    static_assert(old.extent_known && old.within_extent);
    static_assert(old.extent_bytes==12*GiB);
    static_assert(old.tracked_bytes==1280*MiB);
    static_assert(old.not_tracked_bytes==12*GiB-1280*MiB);
    // Separate direct owners are additive; virtual heap/JIT reservations
    // have no fields because they own no physical backing.
    constexpr auto populated = Summarize(12*GiB, {
        .heap_roots=1280*MiB,
        .heap_large=192*MiB,
        .sparse_tables=64*MiB,
        .jit_sparse=256*MiB,
        .jit_dense=384*MiB,
    });
    static_assert(populated.tracked_bytes==2176*MiB);
    static_assert(populated.not_tracked_bytes==12*GiB-2176*MiB);
    constexpr auto unknown = Summarize(-1, {.heap_roots=1280*MiB});
    static_assert(!unknown.extent_known && !unknown.within_extent);
    static_assert(unknown.tracked_bytes==1280*MiB);
    static_assert(unknown.not_tracked_bytes==0);
    constexpr auto exceeded = Summarize(512*MiB, {.heap_roots=600*MiB});
    static_assert(exceeded.extent_known && !exceeded.within_extent);
    static_assert(exceeded.not_tracked_bytes==0);
    constexpr auto overflowed = Summarize(12*GiB, {
        .heap_roots=std::numeric_limits<std::uint64_t>::max(),
        .heap_large=8192,
    });
    static_assert(overflowed.tracked_bytes==std::numeric_limits<std::uint64_t>::max());
    static_assert(!overflowed.within_extent);
    assert(populated.tracked_bytes + populated.not_tracked_bytes == 12*GiB);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-direct-pool-") as work:
    source = Path(work) / "test.cpp"
    exe = Path(work) / "test"
    source.write_text(code)
    subprocess.run([
        compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
        "-I", str(root / "headless"), str(source), "-o", str(exe)],
        check=True, timeout=120)
    subprocess.run([str(exe)], check=True, timeout=120)
print("PASS kernel 12-GiB direct pool vs installed 16-GiB distinction, 1280-MiB Encore heap ledger, ASan/UBSan")
print("Unclassified bytes are NOT confirmed free RAM; no physical Sony mspace unmapping")
