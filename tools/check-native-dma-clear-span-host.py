#!/usr/bin/env python3
"""Compile actual DMA clear/registration methods with byte-span witnesses."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()


def method(name):
    begin = "template <class P>\nbool BufferCache<P>::" + name + "("
    assert source.count(begin) == 1
    return begin + source.split(begin, 1)[1].split("\ntemplate <class P>", 1)[0]


clear = method("DMAClear")
registered = method("IsRegionRegistered")
fixed = "IsRegionRegistered(*cpu_dst_address, size)"
original = clear.replace(fixed, "IsRegionRegistered(*cpu_dst_address, amount)")
cpp = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <optional>
#include <vector>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using DAddr = u64;
using GPUVAddr = u64;
using BufferId = unsigned;
namespace Common { u64 DivCeil(u64 n, u64 d) { return n / d + (n % d != 0); } }
struct Buffer {
    DAddr base{};
    std::size_t size{}, marked{};
    DAddr CpuAddr() { return base; }
    std::size_t SizeBytes() { return size; }
    u32 Offset(DAddr address) { assert(address >= base); return address - base; }
    void MarkUsage(u32 offset, std::size_t bytes) {
        assert(offset + bytes <= size); marked = bytes;
    }
};
struct Mapping {
    bool present = true;
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr address) {
        return present ? std::optional<DAddr>(address) : std::nullopt;
    }
};
template <class P> struct BufferCache {
    static constexpr u32 CACHING_PAGEBITS = 16;
    static constexpr u64 CACHING_PAGESIZE = u64{1} << CACHING_PAGEBITS;
    std::array<BufferId, 4> page_table{};
    std::array<Buffer, 3> slot_buffers{};
    Mapping mapping;
    Mapping* gpu_memory = &mapping;
    struct Ranges { std::size_t bytes{}; unsigned calls{};
        void Subtract(DAddr, std::size_t size) { bytes = size; ++calls; }
    } gpu_modified_ranges;
    struct Runtime {
        std::vector<u32> image = std::vector<u32>(65536, 0x12345678);
        unsigned calls{};
        void ClearBuffer(Buffer& buffer, u32 offset, std::size_t size, u32 value) {
            assert(size % sizeof(u32) == 0);
            const auto first = (buffer.base + offset) / sizeof(u32);
            assert(first + size / sizeof(u32) <= image.size());
            std::fill_n(image.begin() + first, size / sizeof(u32), value);
            ++calls;
        }
    } runtime;
    unsigned downloads{}, finds{};
    std::size_t download_size{};
    void ClearDownload(DAddr, std::size_t size) { ++downloads; download_size = size; }
    BufferId FindBuffer(DAddr address, u32 size, bool insert) {
        assert(!insert); ++finds;
        slot_buffers[2] = Buffer{address, size, 0}; return 2;
    }
    bool DMAClear(GPUVAddr, u64, u32);
    bool IsRegionRegistered(DAddr, std::size_t);
};
__CLEAR__
__REGISTERED__
int main() {
    constexpr DAddr address = 4096;
    constexpr u64 words = 16384, bytes = words * sizeof(u32);
    constexpr u32 pattern = 0xaabbccdd;
    BufferCache<int> late;
    late.slot_buffers[1] = Buffer{65536, 65536, 0}; late.page_table[1] = 1;
    assert(!late.IsRegionRegistered(address, words));
    assert(late.IsRegionRegistered(address, bytes));
    // Only the last part overlaps an existing GPU buffer. A word count used
    // as bytes misses that buffer and leaves the registered GPU data stale.
    assert(late.DMAClear(address, words, pattern));
    assert(late.runtime.calls == 1 && late.finds == 1 && late.downloads == 1);
    assert(late.download_size == bytes && late.gpu_modified_ranges.bytes == bytes);
    assert(late.slot_buffers[2].marked == bytes);
    for (std::size_t i = 0; i < late.runtime.image.size(); ++i)
        assert(late.runtime.image[i] ==
               (i >= address / 4 && i < (address + bytes) / 4 ? pattern : 0x12345678));
    // No registered range: retain the caller's CPU fallback, no GPU work.
    BufferCache<int> absent;
    assert(!absent.DMAClear(address, words, pattern));
    assert(!absent.runtime.calls && !absent.finds && !absent.downloads);
    absent.mapping.present = false;
    assert(!absent.DMAClear(address, words, pattern));
    assert(!absent.runtime.calls && !absent.finds && !absent.downloads);
    // Registration at the beginning still takes the same accelerated route.
    BufferCache<int> early;
    early.slot_buffers[1] = Buffer{0, 65536, 0}; early.page_table[0] = 1;
    assert(early.DMAClear(address, 8, pattern));
    assert(early.download_size == 32 && early.runtime.calls == 1);
    for (const auto invalid : std::array<u64, 4>{0, (u64{1} << 30),
                                               (u64{1} << 30) + 1, ~u64{0}}) {
        BufferCache<int> bounded;
        bounded.slot_buffers[1] = Buffer{0, 65536, 0}; bounded.page_table[0] = 1;
        assert(!bounded.DMAClear(address, invalid, pattern));
        assert(!bounded.runtime.calls && !bounded.finds && !bounded.downloads);
        assert(!bounded.gpu_modified_ranges.calls);
    }
    std::puts("DMA_CLEAR_SPAN_PASS late_overlap=1 fallback_preserved=1 byte_range_exact=1");
}
'''
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-dma-clear-") as temp:
    folder = Path(temp)
    for name, body in (("original", original), ("maintained", clear)):
        path, executable = folder / (name + ".cpp"), folder / name
        path.write_text(cpp.replace("__CLEAR__", body).replace("__REGISTERED__", registered))
        subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        str(path), "-o", str(executable)], check=True, timeout=60)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
        if name == "original":
            assert result.returncode != 0 and "Assertion" in result.stderr, result.stderr
            print("ORIGINAL_DMA_CLEAR_SHORT_SPAN_REPRODUCED")
        else:
            assert result.returncode == 0, result.stderr
            assert fixed in clear, "DMA clear must check the complete byte span"
            print(result.stdout, end="")
print("DMA_CLEAR_HOST_ONLY native_GPU_and_gameplay=unverified")
