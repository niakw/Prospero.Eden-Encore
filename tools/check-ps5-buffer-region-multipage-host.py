#!/usr/bin/env python3
"""Exact BufferCache region-ownership regression for partially covered first pages.

False negatives here can skip guest CPU writes and leave a later registered GPU
buffer stale, even though the monotonic BufferPages witness correctly says
the queried region MAY overlap some buffer.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
active = (root / "vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
backport = (root / "vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h").read_text()
needle = "template <class P>\nbool BufferCache<P>::IsRegionRegistered(DAddr addr, size_t size) {"

def method(source):
    assert source.count(needle) == 1
    begin = source.index(needle)
    return source[begin:source.index("\ntemplate <class P>", begin + len(needle))]

body = method(active)
original = method(backport)
assert original.count("page = Common::DivCeil(end_addr, CACHING_PAGESIZE);") == 1
assert original.count("    const DAddr end_addr = addr + size;") == 1
expected = original.replace("bool BufferCache<P>::IsRegionRegistered(DAddr addr, size_t size) {\n    const DAddr end_addr = addr + size;", "bool BufferCache<P>::IsRegionRegistered(DAddr addr, size_t size) {\n    // An empty CPU write does not overlap any registered cache buffer.\n    if (size == 0) {\n        return false;\n    }\n    // The page_table has exactly 16 GiB of guest-physical address space.\n    // Reject unrepresentable/overflowing spans before addr + size or page_table[].\n    constexpr DAddr kTableAddressLimit = DAddr{1} << 34;\n    if (addr >= kTableAddressLimit || size > kTableAddressLimit - addr) {\n        return false;\n    }\n    const DAddr end_addr = addr + size;").replace(
    "        if (buf_start_addr < end_addr && addr < buf_end_addr) {\n            return true;\n        }\n        page = Common::DivCeil(end_addr, CACHING_PAGESIZE);", "        if (buf_start_addr < end_addr && addr < buf_end_addr) {\n            return true;\n        }\n        // The first page can contain a buffer ending before addr. A later\n        // page may belong to another registered buffer intersecting the span.\n        // Do not skip all remaining pages after one non-overlapping owner.\n        ++page;")
assert body == expected, "native ownership scan differs from reviewed backport transformation"
assert "if (size == 0)" in body
assert body.count("++page;") == 2
assert "page = Common::DivCeil(end_addr, CACHING_PAGESIZE);" not in body
fixture = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
using DAddr = std::uint64_t;
using u64 = std::uint64_t;
static constexpr u64 CACHING_PAGEBITS=12;
static constexpr u64 CACHING_PAGESIZE=1ull << CACHING_PAGEBITS;
namespace Common {
template<class T> T DivCeil(T a, T b) { return a / b + (a % b != 0); }
}
struct BufferId {
    std::size_t value{};
    operator std::size_t() const { return value; }
};
struct Buffer {
    DAddr address{};
    std::size_t size{};
    DAddr CpuAddr() const { return address; }
    std::size_t SizeBytes() const { return size; }
};
template<class P>
struct BufferCache {
    std::vector<BufferId> page_table;
    std::vector<Buffer> slot_buffers;
    bool IsRegionRegistered(DAddr addr, size_t size);
};
""" + body + r"""
int main() {
    BufferCache<void> b;
    b.page_table.resize(8);
    b.slot_buffers = {{}, {0x1000,0x400}, {0x2000,0x800}, {0x3100,0x700}};
    b.page_table[1] = {1};
    b.page_table[2] = {2};
    b.page_table[3] = {3};

    // Prior implementation jumped straight to the end when the first
    // registered page ended before the queried span's starting address.
    // The SECOND page is nevertheless a real overlap and must be visited.
    assert(b.IsRegionRegistered(0x1800,0x1000));
    // A gap must remain a gap; seeing a page owner isn't itself an overlap.
    assert(!b.IsRegionRegistered(0x1800,0x100));
    // Direct single-page overlap still succeeds.
    assert(b.IsRegionRegistered(0x1100,0x100));
    // Skipping an unowned intermediate page must not lose page three.
    b.page_table[2] = {};
    assert(b.IsRegionRegistered(0x1800,0x2000));
    // All actual owners absent from the queried range means false.
    assert(!b.IsRegionRegistered(0x1800,0x1600));
    // An empty write is not an overlapping write, even inside a buffer.
    assert(!b.IsRegionRegistered(0x1100,0));
    // Independent direct registration on the later page.
    assert(b.IsRegionRegistered(0x3200,0x80));
    // The actual native page_table is bounded to 16 GiB. Invalid spans
    // must return BEFORE attempting a page_table[] lookup; this small fixture
    // deliberately keeps only eight pages, and UBSan checks the range logic.
    constexpr DAddr limit = DAddr{1} << 34;
    assert(!b.IsRegionRegistered(limit, 1));
    assert(!b.IsRegionRegistered(limit + 0x1000, 1));
    assert(!b.IsRegionRegistered(limit - 0x80, 0x100));
    assert(!b.IsRegionRegistered(~DAddr{0} - 2, 8));
    assert(!b.IsRegionRegistered(~DAddr{0}, 1));
    // A zero-sized query at the maximum address remains a no-op.
    assert(!b.IsRegionRegistered(~DAddr{0}, 0));
}
"""
compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "Host C++ compiler required"
with tempfile.TemporaryDirectory(prefix="encore-region-multipage-") as folder:
    source = Path(folder) / "region.cpp"
    source.write_text(fixture)
    for opt in ("-O0", "-O2"):
        exe = Path(folder) / ("region" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", str(source), "-o", str(exe)],
                       check=True, timeout=45)
        subprocess.run([str(exe)], check=True, timeout=20)
        print("BUFFER_REGION_MULTIPAGE_HOST_PASS", opt)
