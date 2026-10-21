#!/usr/bin/env python3
"""Compile selected native DMA copy spans before any u64 -> u32 narrowing."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
core=(root/"vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
active=(root/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
bridge=(root/"vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp").read_text()
core_start="bool BufferCache<P>::DMACopy(GPUVAddr src_address, GPUVAddr dest_address, u64 amount) {"
end="    const bool source_dirty = IsRegionRegistered(*cpu_src_address, amount);"
block=core[core.index(core_start):core.index(end,core.index(core_start))]
assert "if (amount == 0 || amount > static_cast<u64>(~u32{0}))" in block
assert block.index("if (amount == 0") < block.index("gpu_memory->GpuToCpuAddress(src_address)")
rest=core[core.index(end,core.index(core_start)):core.index("bool BufferCache<P>::DMAClear(",core.index(core_start))]
for pattern in ("FindBuffer(*cpu_src_address, static_cast<u32>(amount), false)",
                "FindBuffer(*cpu_dest_address, static_cast<u32>(amount), false)",
                "SynchronizeBuffer(src_buffer, *cpu_src_address, static_cast<u32>(amount))"):
    assert pattern in rest
wrap_begin="bool AccelerateDMA::BufferCopy(GPUVAddr src_address, GPUVAddr dest_address, u64 amount) {"
wrap_end="\ntemplate <bool IS_IMAGE_UPLOAD>"
def grab(s):
    a=s.index(wrap_begin)
    return s[a:s.index(wrap_end,a)].rstrip()
wrapper=grab(active)
assert wrapper==grab(bridge)
assert wrapper.index("if (amount == 0") < wrapper.index("std::scoped_lock lock{buffer_cache.mutex};")
oracle=(root/"tools/prepare-vulkan-port.py").read_text()
assert "empty/oversized copy before the guest buffer-cache mutex" in oracle
contract=(root/"tools/check-ps5-buffer-pages-r437.py").read_text()
assert "# DMA copy's byte count also reaches FindBuffer(u32)" in contract
cmake=(root/"headless/CMakeLists.txt").read_text()
assert 'configure_file("${EDEN_MAINTAINED_BUFFER_PAGES}"' in cmake
preamble=r"""
#include <cassert>
#include <cstdint>
#include <mutex>
#include <optional>
#include <limits>
using u64 = std::uint64_t;
using u32 = std::uint32_t;
using DAddr = std::uint64_t;
using GPUVAddr = std::uint64_t;
struct Memory {
    unsigned translations=0;
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr a) {
        ++translations;
        return a;
    }
};
template<class P>
struct BufferCache {
    Memory owner;
    Memory* gpu_memory=&owner;
    bool DMACopy(GPUVAddr,GPUVAddr,u64);
};
"""
source=preamble+ "template<class P>\n"+block+ r"""
    // The core's range tracking begins after this point. The proof checks
    // that invalid lengths cannot reach it.
    return true;
}
struct CountingMutex {
    std::mutex inner;
    unsigned locks=0;
    void lock(){inner.lock();++locks;}
    void unlock(){inner.unlock();}
};
struct RasterBuffer {
    CountingMutex mutex;
    unsigned copy_calls=0;
    bool DMACopy(GPUVAddr,GPUVAddr,u64){++copy_calls;return true;}
};
struct AccelerateDMA {
    RasterBuffer buffer_cache;
    bool BufferCopy(GPUVAddr,GPUVAddr,u64);
};
""" + wrapper + r"""
int main() {
    constexpr u64 max=static_cast<u64>(std::numeric_limits<u32>::max());
    BufferCache<int> inner;
    AccelerateDMA outer;
    for(const u64 size : {u64{0}, max+1, std::numeric_limits<u64>::max()}) {
        assert(!inner.DMACopy(0x1000,0x2000,size));
        assert(!outer.BufferCopy(0x1000,0x2000,size));
        assert(inner.owner.translations==0);
        assert(outer.buffer_cache.mutex.locks==0);
        assert(outer.buffer_cache.copy_calls==0);
    }
    for(const u64 size : {u64{1}, max}) {
        assert(inner.DMACopy(0x1000,0x2000,size));
        assert(outer.BufferCopy(0x1000,0x2000,size));
    }
    assert(inner.owner.translations==4);
    assert(outer.buffer_cache.mutex.locks==2);
    assert(outer.buffer_cache.copy_calls==2);
}
"""
with tempfile.TemporaryDirectory(prefix="encore-dma-copy-span-") as tmp:
    cpp=Path(tmp)/"main.cpp";cpp.write_text(source)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/opt
        subprocess.run(["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror","-pthread",
                        str(cpp),"-o",str(exe)],check=True,timeout=30)
        subprocess.run([str(exe)],check=True,timeout=10)
        print("ENCORE_DMA_COPY_SPAN_PASS",opt)
