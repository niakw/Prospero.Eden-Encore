#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile source-extracted PS5 direct extent cache against concurrent host mocks.

NOT a firmware test: exercises the real C++ helper and its positive-only
atomic cache on a Linux runner during the explicit next-build source gates.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
s = (root / "src/memory_pages.cpp").read_text()
begin = s.index("namespace {\n// This is the fixed addressable direct-memory EXTENT")
end = s.index("} // namespace\n#endif", begin) + len("} // namespace")
helper = s[begin:end]
assert helper.count("sceKernelGetDirectMemorySize()") == 1
assert "cached_direct_memory_extent.store(current, std::memory_order_release)" in helper
assert "return extent > 0 ? sceKernelAllocateDirectMemory(" in helper
compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
if not compiler:
    raise SystemExit("C++20 compiler required for direct-memory extent host gate")

head = r"""
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <thread>
#include <vector>

static std::atomic<unsigned> extent_queries{};
static std::atomic<unsigned> issued_allocations{};
static std::atomic<bool> fail_first{true};
static std::int64_t sceKernelGetDirectMemorySize() {
    extent_queries.fetch_add(1);
    return fail_first.exchange(false) ? -1 : (std::int64_t{12} << 30);
}
static std::int32_t sceKernelAllocateDirectMemory(
    std::int64_t begin, std::int64_t limit, std::size_t bytes,
    std::size_t alignment, int type, std::int64_t* physical) {
    assert(begin == 0 && limit == (std::int64_t{12} << 30));
    assert(bytes == 2u * 1024 * 1024 && alignment == bytes && type == 12);
    assert(physical);
    *physical = 0x12000;
    issued_allocations.fetch_add(1);
    return 0;
}
"""
tail = r"""
int main() {
    std::int64_t physical = -1;
    // An unknown/negative kernel response must not call the physical alloc.
    assert(AllocateDirectOwned(2u << 20, 2u << 20, &physical) != 0);
    assert(extent_queries.load() == 1 && issued_allocations.load() == 0);
    assert(AllocateDirectOwned(2u << 20, 2u << 20, &physical) == 0);
    assert(extent_queries.load() == 2 && issued_allocations.load() == 1);
    std::vector<std::thread> threads;
    for (unsigned i = 0; i < 8; ++i)
        threads.emplace_back([] {
            for (unsigned j = 0; j < 20000; ++j) {
                std::int64_t owned = -1;
                assert(AllocateDirectOwned(2u << 20, 2u << 20, &owned) == 0);
                assert(owned == 0x12000);
            }
        });
    for (auto& thread : threads) thread.join();
    assert(extent_queries.load() == 2);
    assert(issued_allocations.load() == 1 + 8 * 20000u);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-dmem-extent-") as tmp:
    folder = Path(tmp)
    src, exe = folder / "extent.cpp", folder / "extent"
    src.write_text(head + helper + tail)
    subprocess.run([compiler, "-std=c++20", "-O2", "-pthread", "-Wall", "-Wextra",
                    "-Werror", str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("PASS: real direct-memory extent cache retries initial error and reuses one positive result across 8 threads")
print("Firmware native direct-memory allocation and frame-time effect remain UNTESTED")
