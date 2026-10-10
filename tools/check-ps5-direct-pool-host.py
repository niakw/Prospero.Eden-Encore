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
probe_policy = (root / "headless/direct_pool_probe_policy.h").read_text()
region_policy = (root / "headless/direct_pool_region_scan.h").read_text()
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
assert 'IsKernelFreeSpanValid(' in header
assert 'IsKernelFreeSpanValid(total, start, observed)' in perf
assert 'IsKernelFreeSpanValid(cached_direct_total, start, largest)' in perf
assert 'IsKernelFreeSpanValid(total, largest_start, largest)' in perf
assert 'const bool largest_valid = largest_rc == 0' in perf
assert 'unsigned(account.within_extent), unsigned(largest_valid),' in perf
assert 'largest_start=%lld largest_valid=%u free_upper=' in perf
assert '#include "direct_pool_probe_policy.h"' in perf
assert '#include "direct_pool_region_scan.h"' in perf
assert '::Eden::DirectPool::RegionScan scan{total};' in perf
assert 'static std::atomic<bool> direct_region_scan_enabled{false};' in perf
assert 'direct_region_scan_enabled.load(std::memory_order_acquire)' in perf
assert 'if (scan_requested) {' in perf
assert 'unsigned scan_stop = scan_requested ? 0u : 4u;' in perf
assert 'scan_requested && scan.valid' in perf
assert '? static_cast<long long>(scan.FreeUpperBound()) : -1LL;' in perf
assert 'memory-region-scan.txt' in (root / "headless/main.cpp").read_text()
assert 'SetDirectMemoryRegionScanEnabled(' in (root / "headless/main.cpp").read_text()
assert 'SetDirectMemoryRegionScanEnabled(bool enabled) noexcept;' in (root / "headless/performance.h").read_text()
assert perf.index('if (scan_requested) {') < perf.index('sceKernelDirectMemoryQuery(scan.cursor')
assert 'scan.Include(region.start, region.end)' in perf
assert 'const long long free_upper = static_cast<long long>(scan.FreeUpperBound());' in perf
assert 'scan_reached_extent=%u scan_stop=%u query_rc=%d short=%d' in perf
assert 'scan.ReachedExtent()' in perf
assert "NEVER allocatable or a JIT/GPU budget" in region_policy
assert '::Eden::DirectPool::ProbeIntervalNs(' in perf
assert 'kProbeHighHeadroomBytes = 4ULL << 30' in probe_policy
assert "std::numeric_limits<std::uint64_t>::max()" in header
assert "return {extent, used, 0, true, false};" in header
assert "return {extent, used, extent - used, true, true};" in header
assert "untracked is not free" in perf.lower(), "Do not present unclassified as free"
assert 'void ResetDirectMemoryProbeForTitle() noexcept' in perf
assert 'if (query_in_flight.load(std::memory_order_acquire)) std::abort();' in perf
assert 'largest_free_block.store(0, std::memory_order_relaxed);' in perf
assert 'has_valid_sample.store(false, std::memory_order_release);' in perf
assert 'checked_ns.store(0, std::memory_order_release);' in perf
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
#include "direct_pool_probe_policy.h"
#include "direct_pool_region_scan.h"
int main() {
    using namespace Eden::DirectPool;
    constexpr std::uint64_t MiB = 1024ULL * 1024;
    constexpr std::uint64_t GiB = 1024ULL * MiB;
    // Probe cadence must not ignore a missed sample or pressure; only the
    // kernel-confirmed high-headroom path may skip 100-ms/200-ms queries.
    static_assert(ProbeIntervalNs(false, 0, 12*GiB) == kProbeFastNs);
    static_assert(ProbeIntervalNs(true, 1, 12*GiB) == kProbeFastNs);
    static_assert(ProbeIntervalNs(true, 2, 12*GiB) == kProbeFastNs);
    static_assert(ProbeIntervalNs(true, 0, 4*GiB-MiB) == kProbeFastNs);
    static_assert(ProbeIntervalNs(true, 0, 4*GiB) == kProbeHighHeadroomNs);
    static_assert(ProbeIntervalNs(true, 0, 8*GiB) == kProbeHighHeadroomNs);
    // An invalid kernel-free span must never drive the dense JIT plan
    // or graphics admission. Check negative start, too-large length,
    // exact boundary, zero known availability and extreme integer values.
    static_assert(IsKernelFreeSpanValid(12*GiB, 0, 12*GiB));
    static_assert(IsKernelFreeSpanValid(12*GiB, 4*GiB, 8*GiB));
    static_assert(IsKernelFreeSpanValid(12*GiB, 12*GiB, 0));
    static_assert(!IsKernelFreeSpanValid(12*GiB, 4*GiB, 9*GiB));
    static_assert(!IsKernelFreeSpanValid(12*GiB, -1, 1));
    static_assert(!IsKernelFreeSpanValid(12*GiB, 12*GiB+1, 0));
    static_assert(!IsKernelFreeSpanValid(0, 0, 0));
    static_assert(!IsKernelFreeSpanValid(-1, 0, 0));
    static_assert(!IsKernelFreeSpanValid(12*GiB, 0, std::numeric_limits<std::size_t>::max()));
    // Interrupted enumeration must not become a fictional pool budget.
    RegionScan partial{12*GiB};
    assert(partial.Include(1*GiB, 2*GiB));
    assert(partial.Include(4*GiB, 5*GiB));
    assert(partial.regions == 2);
    assert(partial.FreeUpperBound() == 10*GiB);
    assert(!partial.ReachedExtent()); // query stopped in an unmapped tail
    RegionScan overlap{12*GiB};
    assert(overlap.Include(1*GiB, 2*GiB));
    assert(!overlap.Include(1*GiB, 3*GiB));
    assert(!overlap.valid && overlap.FreeUpperBound() == -1);
    RegionScan bad_extent{12*GiB};
    assert(!bad_extent.Include(11*GiB, 13*GiB));
    assert(bad_extent.FreeUpperBound() == -1);
    RegionScan monotone{12*GiB};
    assert(monotone.Include(0, 2*GiB));
    assert(monotone.Include(3*GiB, 12*GiB));
    assert(monotone.ReachedExtent());
    assert(monotone.FreeUpperBound() == 1*GiB);
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
print("PASS kernel direct-memory region scan: incomplete enumeration cannot claim full physical pool")
print("PASS 100-ms pressure/unknown probe cadence, 250-ms only for >=4 GiB confirmed contiguous headroom")
print("PASS JIT/GPU free-span admission refuses successful-but-out-of-range kernel replies")
