#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Backport exactly Eden mirror #4473 (2026-09-24) to derived build sources.

Origin dbeb73ee011416cffc6c203945f5ccc6b90621f6.
Upstream copyrights remain in derived files. Vendored archives stay immutable.
"""
import argparse
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

REWRITES = {
    "buffer_cache/buffer_cache.h": [
        ("if (memory_tracker.IsRegionGpuModified(device_addr, size)) {",
         "if (IsRegionGpuModified(device_addr, size)) {"),
        ("""        const DAddr device_addr_start = Common::AlignDown(device_addr, 64);
        const DAddr device_addr_end = Common::AlignUp(device_addr + size, 64);
        const size_t new_size = device_addr_end - device_addr_start;
        ClearDownload(device_addr_start, new_size);
        gpu_modified_ranges.Subtract(device_addr_start, new_size);""",
         """        ClearDownload(device_addr, size);
        gpu_modified_ranges.Subtract(device_addr, size);"""),
        ("""    memory_tracker.ForEachUploadRange(device_addr, size, [&](u64 device_addr_out, u64 range_size) {
        upload_copies.push_back(BufferCopy{
            .src_offset = total_size_bytes,
            .dst_offset = device_addr_out - buffer_start,
            .size = range_size,
        });
        total_size_bytes += range_size;
        largest_copy = (std::max)(largest_copy, range_size);
    });""",
         """    const auto add_upload = [&](DAddr start, DAddr end) {
        if (start == end) return;
        const u64 range_size = end - start;
        upload_copies.push_back(BufferCopy{
            .src_offset = total_size_bytes,
            .dst_offset = start - buffer_start,
            .size = range_size,
        });
        total_size_bytes += range_size;
        largest_copy = (std::max)(largest_copy, range_size);
    };
    memory_tracker.ForEachUploadRange(device_addr, size, [&](u64 device_addr_out, u64 range_size) {
        DAddr upload_start = device_addr_out;
        gpu_modified_ranges.ForEachInRange(device_addr_out, range_size, [&](DAddr gpu_start, DAddr gpu_end) {
            add_upload(upload_start, gpu_start);
            upload_start = gpu_end;
        });
        add_upload(upload_start, device_addr_out + range_size);
    });"""),
    ],
    "engines/kepler_compute.h": [
        ("    GPUVAddr upload_address;\n\n    struct UploadInfo {",
         "    GPUVAddr upload_address;\n    bool upload_dirty{};\n\n    struct UploadInfo {"),
        ("        u32 copy_size;\n    };\n    std::vector<UploadInfo> uploads;",
         "        u32 copy_size;\n        bool was_dirty;\n    };\n    std::vector<UploadInfo> uploads;"),
    ],
    "engines/kepler_compute.cpp": [
        ("                        .copy_size = upload_state.GetUploadSize()};",
         "                        .copy_size = upload_state.GetUploadSize(),\n                        .was_dirty = upload_dirty};"),
        ("        upload_address = current_dma_segment;\n        upload_state.ProcessData(method_argument, is_last_call);",
         "        upload_address = current_dma_segment;\n        upload_dirty = current_dirty;\n        current_dirty = false;\n        upload_state.ProcessData(method_argument, is_last_call);"),
        ("        upload_address = current_dma_segment;\n        upload_state.ProcessData(base_start, amount);",
         "        upload_address = current_dma_segment;\n        upload_dirty = current_dirty;\n        current_dirty = false;\n        upload_state.ProcessData(base_start, amount);"),
        ("""            if (offset / sizeof(u32) == LAUNCH_REG_INDEX(grid_dim_x) &&
                memory_manager.IsMemoryDirty(data.upload_address, data.copy_size)) {
                indirect_compute = {data.upload_address};
            }""",
         """            if (offset / sizeof(u32) == LAUNCH_REG_INDEX(grid_dim_x)) {
                const bool source_dirty = memory_manager.IsMemoryDirty(data.upload_address, data.copy_size);
                if (data.was_dirty || source_dirty) {
                    indirect_compute = {data.upload_address};
                }
            }"""),
    ],
    "dma_pusher.cpp": [
        ("[[maybe_unused]] constexpr u32 ComputeInline = 0x6D;",
         "constexpr u32 ComputeInline = 0x6D;"),
        ("""    if (header.size > 0 && dma_state.method >= MacroRegistersStart && subchannels[dma_state.subchannel]) {
        subchannels[dma_state.subchannel]->current_dirty = memory_manager.IsMemoryDirty(dma_state.dma_get, header.size * sizeof(u32));
    }

    if (header.size > 0) {""",
         """    if (header.size > 0) {
        if (subchannels[dma_state.subchannel] && dma_state.method_count) {
            const auto engine = subchannel_type[dma_state.subchannel];
            const bool kepler_payload = engine == Engines::EngineTypes::KeplerCompute && dma_state.method == ComputeInline && dma_state.non_incrementing;
            const bool macro_payload = engine == Engines::EngineTypes::Maxwell3D && dma_state.method >= MacroRegistersStart;
            if (kepler_payload || macro_payload) {
                const size_t words = std::min<size_t>(dma_state.method_count, header.size);
                subchannels[dma_state.subchannel]->current_dirty = memory_manager.IsMemoryDirty(dma_state.dma_get, words * sizeof(u32));
            }
        }"""),
    ],
}

def apply(src_root: Path, dest: Path) -> dict[str, Path]:
    outputs = {}
    for key, changes in REWRITES.items():
        source = src_root / key
        data = source.read_text()
        for i, (before, after) in enumerate(changes, 1):
            count = data.count(before)
            if count != 1:
                raise RuntimeError(f"Upstream #4473 incompatible {key} hunk={i} count={count}")
            data = data.replace(before, after, 1)
        relative = Path("video_core") / key if key.endswith(".h") else Path(key).name
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_text() != data:
            temp = target.with_suffix(target.suffix + ".in")
            temp.write_text(data)
            temp.replace(target)
        outputs[key] = target
    return outputs

def self_test(source_root: Path):
    with tempfile.TemporaryDirectory(prefix="eden-4473-") as name:
        paths = apply(source_root, Path(name))
        buffer = paths["buffer_cache/buffer_cache.h"].read_text()
        kepler_h = paths["engines/kepler_compute.h"].read_text()
        kepler_cpp = paths["engines/kepler_compute.cpp"].read_text()
        dma = paths["dma_pusher.cpp"].read_text()
        assert "IsRegionGpuModified(device_addr, size)" in buffer
        assert "AlignDown(device_addr, 64)" not in buffer
        assert "gpu_modified_ranges.ForEachInRange(device_addr_out, range_size" in buffer
        assert "bool upload_dirty{};" in kepler_h
        assert "bool was_dirty;" in kepler_h
        assert kepler_cpp.count("upload_dirty = current_dirty;") == 2
        assert "data.was_dirty || source_dirty" in kepler_cpp
        assert "std::min<size_t>(dma_state.method_count, header.size)" in dma
        assert "dma_state.method == ComputeInline && dma_state.non_incrementing" in dma
        assert "header.size * sizeof(u32)" not in dma

        # Compile the actual resulting upload-split lambda, not a rewritten
        # Python simulation. GPU-owned subranges must remain untouched.
        start = buffer.index("    const auto add_upload = [&]")
        end = buffer.index("    if (total_size_bytes == 0)", start)
        snippet = buffer[start:end]
        cpp = r'''
#include <cassert>
#include <algorithm>
#include <cstdint>
#include <utility>
#include <vector>
using u64 = std::uint64_t;
using DAddr = std::uint64_t;
struct BufferCopy { u64 src_offset, dst_offset, size; };
struct MemoryTracker {
 template<typename F> void ForEachUploadRange(DAddr, u64, F&& f) const { f(1000, 100); }
} memory_tracker;
struct Owned {
 template<typename F> void ForEachInRange(DAddr begin, u64 len, F&& f) const {
  for (auto [a,b] : std::vector<std::pair<DAddr,DAddr>>{{1020,1040},{1060,1080}}) {
   auto lo = std::max(a, begin), hi = std::min(b, begin+len);
   if(lo < hi) f(lo,hi);
  }
 }
} gpu_modified_ranges;
int main() {
 const DAddr buffer_start = 1000, device_addr = 1000;
 const u64 size = 100;
 std::vector<BufferCopy> upload_copies;
 u64 total_size_bytes=0, largest_copy=0;
__SNIPPET__
 assert(upload_copies.size() == 3);
 assert(upload_copies[0].dst_offset==0 && upload_copies[0].size==20);
 assert(upload_copies[1].dst_offset==40 && upload_copies[1].size==20);
 assert(upload_copies[2].dst_offset==80 && upload_copies[2].size==20);
 assert(total_size_bytes==60 && largest_copy==20);
}
'''.replace("__SNIPPET__", snippet)
        compiler = next((n for n in ("clang++-18", "clang++", "g++") if shutil.which(n)), None)
        if not compiler:
            raise RuntimeError("Host C++20 compiler required")
        src = Path(name) / "ownership.cpp"
        exe = Path(name) / "ownership"
        src.write_text(cpp)
        subprocess.run([compiler, "-std=c++20", "-O1", "-Wall", "-Wextra",
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        str(src), "-o", str(exe)], check=True, timeout=50)
        subprocess.run([str(exe)], check=True, timeout=30)
    print("PASS Eden upstream #4473 four-source backport, actual C++ upload ownership ASan/UBSan")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path,
                        default=Path(__file__).resolve().parents[1] / "vendor/sources/eden/src/video_core")
    parser.add_argument("--dest", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        cmake_file = (Path(__file__).resolve().parents[1] / "headless/CMakeLists.txt").read_text()
        marker = 'target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/gpu-memory-4473")'
        assert cmake_file.count(marker) == 1
        assert cmake_file.index('include("${EDEN_PORT_DIR}/vulkan.cmake")') < cmake_file.index(marker)
        assert 'file(READ "${PORT_BUILD_DIR}/gpu-memory-4473/dma_pusher.cpp" command_source)' in cmake_file
        self_test(args.source)
    else:
        if args.dest is None:
            parser.error("--dest required without --self-test")
        apply(args.source, args.dest)
        print("Eden upstream #4473: patched four derived GPU ownership sources")
