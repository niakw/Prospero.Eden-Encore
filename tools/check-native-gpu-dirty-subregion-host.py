#!/usr/bin/env python3
"""Host sanitizer regression for 2-KiB GPU dirty mask boundaries.

Checks actual native source-derivation anchors and the exact 32-bit mask
construction on the split chunks. This is not a console/Vulkan test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
memory = (root / "vendor/sources/eden/src/core/memory.cpp").read_text()
device = (root / "vendor/sources/eden/src/core/device_memory_manager.h").read_text()
dirty = (root / "vendor/sources/eden/src/core/gpu_dirty_memory_manager.h").read_text()
port = (root / "headless/CMakeLists.txt").read_text()
header = (root / "headless/gpu_dirty_region_split.h").read_text()
replay = (root / "headless/gpu_deferred_replay.h").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()

for source, token in (
    (device, "constexpr size_t DEVICE_PAGEBITS = 12ULL;"),
    (dirty, "constexpr static size_t page_bits = DEVICE_PAGEBITS - 1;"),
    (dirty, "constexpr static size_t align_bits = 6U;"),
    (dirty, "TransformAddress BuildTransform(PAddr address, size_t size)"),
    (dirty, "T mask = ~T(0);"),
    (memory, "gpu_dirty_managers[core].Collect(address, size);"),
    (port, "Pinned native GPUDirty Collect call changed"),
    (port, "::Eden::GpuDirty::ForEachRegion(address, size,"),
    (port, 'string(PREPEND eden_cpu_memory "#include'),
    (header, "inline constexpr std::uint64_t kRegionBytes = 2048;"),
    (replay, "inline constexpr std::uint64_t kDirtyRegionBytes = 2048;"),
    (workflow, "python3 -B tools/check-native-gpu-dirty-subregion-host.py"),
):
    assert token in source, token

assert port.index("Pinned native GPUDirty Collect call changed") < port.index(
    "set(eden_native_memory_tu")
assert port.count("gpu_dirty_managers[core].Collect(subaddress, span);") == 1
assert port.count("::Eden::GpuDirty::ForEachRegion(address, size,") == 1

# Embed the ACTUAL pinned original mask builder, rather than a
# hand-transcribed equivalent. The negative control must trip UBSan at 4KiB
# while the bounded splitter must keep every call within 32 mask bits.
mask_begin = "    template <typename T>" + chr(10) + "    T CreateMask("
mask_end = "    TransformAddress BuildTransform("
assert dirty.count(mask_begin) == 1 and dirty.count(mask_end) == 1
mask_source = mask_begin + dirty.split(mask_begin, 1)[1].split(mask_end, 1)[0]

cpp = r"""
#include "gpu_dirty_region_split.h"
#include "core/gpu_dirty_memory_manager.h"
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <limits>
#include <set>
#include <utility>
#include <vector>
using namespace Eden::GpuDirty;
struct ActualPinnedMask {
@@MASK_SOURCE@@
};

void Verify(std::uint64_t address, std::uint64_t bytes) {
    std::uint64_t cursor = address, total = 0;
    unsigned emitted = 0;
    ForEachRegion(address, bytes, [&](std::uint64_t position, std::uint64_t size) {
        assert(position == cursor);
        assert(size > 0 && size <= kRegionBytes);
        assert(position / kRegionBytes == (position + size - 1) / kRegionBytes);
        const std::uint64_t offset = position % kRegionBytes;
        const auto low = offset / 64;
        const auto high = (offset + size + 63) / 64;
        // Exact GPUDirtyMemoryManager::CreateMask<u32> shifts.
        assert(high > 0 && high <= 32 && low < 32);
        const auto mask = ActualPinnedMask{}.CreateMask<std::uint32_t>(high, low);
        for (unsigned cell = 0; cell < 32; ++cell) {
            const bool covered = ((cell + 1) * 64 > offset) &&
                                 (cell * 64 < offset + size);
            assert(bool(mask & (std::uint32_t{1} << cell)) == covered);
        }
        cursor += size;
        total += size;
        ++emitted;
    });
    assert(total == bytes && cursor == address + bytes);
    assert((bytes == 0) == (emitted == 0));
}

// Unlike the mask-only fixture, this path executes the actual pinned
// GPUDirtyMemoryManager::Collect and Gather implementation after splitting.
void VerifyCollector(std::uint64_t address, std::uint64_t bytes) {
    Core::GPUDirtyMemoryManager manager;
    ForEachRegion(address, bytes, [&](std::uint64_t a, std::uint64_t n) {
        manager.Collect(a, static_cast<std::size_t>(n));
    });
    std::set<std::uint64_t> observed, expected;
    std::function<void(PAddr, std::size_t)> gather = [&](PAddr a, std::size_t n) {
        assert((a % 64) == 0 && n != 0 && (n % 64) == 0);
        for (std::uint64_t part = a; part < a + n; part += 64) {
            observed.insert(part);
        }
    };
    manager.Gather(gather);
    if (bytes) {
        for (std::uint64_t part = address & ~std::uint64_t{63};
             part < address + bytes; part += 64) {
            expected.insert(part);
        }
    }
    assert(observed == expected);
}

int main(int argc, char**) {
    if (argc > 1) {
        // Original 4KiB tracked write: top_bit=64 on a 32-bit mask.
        volatile std::size_t top_bit = 64;
        (void)ActualPinnedMask{}.CreateMask<std::uint32_t>(top_bit, 0);
        return 0; // UndefinedBehaviorSanitizer must abort first.
    }
    unsigned calls = 0;
    ForEachRegion(0x1000, 4096, [&](std::uint64_t a, std::uint64_t n) {
        assert(a == 0x1000 + calls * 2048 && n == 2048);
        ++calls;
    });
    assert(calls == 2);
    calls = 0;
    ForEachRegion(0x17fc, 16, [&](std::uint64_t a, std::uint64_t n) {
        if (calls == 0) assert(a == 0x17fc && n == 4);
        if (calls == 1) assert(a == 0x1800 && n == 12);
        ++calls;
    });
    assert(calls == 2);
    for (const auto& [addr, bytes] : std::vector<std::pair<std::uint64_t, std::uint64_t>>{
        {0,0},{0,1},{63,2},{2047,1},{2047,2},{2047,4096},
        {2048,2048},{4095,64},{8190,8193},{0x1000,4096},
        {0x100000,65536},{std::numeric_limits<std::uint64_t>::max()-8192,4096}
    }) Verify(addr, bytes);

    for (const auto& [addr, bytes] :
         std::vector<std::pair<std::uint64_t, std::uint64_t>>{
            {0,0}, {0x17fc,16}, {0x1000,4096}, {0x1001,4096},
            {0x17ff,4097}, {0x1800,2048}, {0x10000,65536},
            {0x3fff,1}, {0x3fff,8193}, {0x1001,0}
         }) {
        VerifyCollector(addr, bytes);
    }
    std::uint64_t actual_seed = 0xafe93b42db5127ULL;
    for (unsigned i = 0; i < 256; ++i) {
        actual_seed = actual_seed * 2862933555777941757ULL + 3037000493ULL;
        const std::uint64_t addr = 0x100000 + ((actual_seed >> 17) % 8192);
        const std::uint64_t length = (actual_seed >> 41) % 8193;
        VerifyCollector(addr, length);
    }

    std::uint64_t seed = 0x56fb984bf129ace3ULL;
    for (unsigned i = 0; i < 5000; ++i) {
        seed = seed * 2862933555777941757ULL + 3037000493ULL;
        const std::uint64_t addr = (seed >> 13) % (1ULL<<36);
        const std::uint64_t size = (seed >> 39) % 8193;
        Verify(addr, size);
    }
}
"""
cpp = cpp.replace("@@MASK_SOURCE@@", mask_source)
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 required"
with tempfile.TemporaryDirectory(prefix="encore-gpu-dirty-host-") as directory:
    unit = Path(directory) / "dirty.cpp"
    binary = Path(directory) / "dirty"
    unit.write_text(cpp)
    # Use the actual checked-in GPU dirty collector, with only its unrelated
    # device address-space header replaced by the same minimal fixture as
    # check-deferred-native-bridge-contract.py.
    stub_dir = Path(directory) / "core"
    stub_dir.mkdir()
    (stub_dir / "gpu_dirty_memory_manager.h").write_text(dirty)
    (stub_dir / "device_memory_manager.h").write_text(
        "#pragma once\n#include <cstddef>\n#include <cstdint>\n"
        "using PAddr = std::uint64_t;\nusing u32 = std::uint32_t;\n"
        "using u64 = std::uint64_t;\n"
        "namespace Core { inline constexpr std::size_t DEVICE_PAGEBITS = 12; }\n"
    )
    subprocess.run(
        [clang, "-std=c++20", "-O1", "-g", "-pthread", "-Wall", "-Wextra",
         "-Werror", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
         "-I", str(root / "headless"), "-I", str(directory),
         str(unit), "-o", str(binary)],
        check=True, timeout=45
    )
    subprocess.run([str(binary)], check=True, timeout=45)
    negative = subprocess.run(
        [str(binary), "--original-unbounded-4k"], capture_output=True,
        text=True, timeout=45
    )
    assert negative.returncode != 0 and "runtime error" in negative.stderr
    assert "shift exponent" in negative.stderr, negative.stderr

print("NATIVE_GPU_DIRTY_SUBREGION_HOST_PASS regions=2048 mask_bits=32 alignment=64 crossings=1 whole_page=1 randomized=5000 original_4k_ubsan_negative_control=1 actual_collect_gather=266")
