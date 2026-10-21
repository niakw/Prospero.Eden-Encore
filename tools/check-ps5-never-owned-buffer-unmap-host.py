#!/usr/bin/env python3
"""Compile native RasterizerVulkan::UnmapMemory and check exact cache lock semantics."""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
active=(root/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
bridge=(root/"vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp").read_text()
start="void RasterizerVulkan::UnmapMemory("
end="void RasterizerVulkan::ModifyGPUMemory("
def get(s):
    a=s.index(start)
    return s[a:s.index(end,a)]
source=get(active)
assert source==get(bridge), "DEV bridge must follow native Unmap source"
assert source.count("::Eden::BufferPages::NeverRegistered(addr, size)")==1
assert source.index("texture_cache.UnmapMemory(addr, size)") < source.index("buffer_cache.WriteMemory(addr, size)") < source.index("pipeline_cache.OnCacheInvalidation(addr, size)")
oracle=(root/"tools/prepare-vulkan-port.py").read_text()
assert "The CPU Unmap path may skip ONLY buffer invalidation" in oracle
owner=(root/"vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
fragment=owner[owner.index("void BufferCache<P>::ChangeRegister("):]
assert fragment.index("::Eden::BufferPages::Mark(buffer.CpuAddr(), size);") < fragment.index("page_table[page] = buffer_id;")
tracker=(root/"vendor/sources/eden/src/video_core/buffer_cache/word_manager.h").read_text()
assert "std::fill_n(heap.data() + size_t(Type::CPU) * num_words, num_words, ~u64{0});" in tracker
cmake=(root/"headless/vulkan.cmake").read_text()
assert '"${PORT_BUILD_DIR}/vulkan_rasterizer.cpp"' in cmake
host=r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include "buffer_pages.h"
using DAddr = std::uint64_t;
using u64 = std::uint64_t;
struct CountMutex {
    std::mutex backing;
    int locks=0;
    void lock() { backing.lock(); ++locks; }
    void unlock() { backing.unlock(); }
};
struct TextureCache {
    CountMutex mutex;
    int unmaps=0;
    void UnmapMemory(DAddr,u64) { ++unmaps; }
};
struct BufferCache {
    CountMutex mutex;
    int writes=0;
    void WriteMemory(DAddr,u64) { ++writes; }
};
struct PipelineCache {
    int invalidations=0;
    void OnCacheInvalidation(DAddr,u64) { ++invalidations; }
};
namespace Eden::ImagePages {
    inline bool held=false;
    bool NeverHeld(DAddr,u64) { return !held; }
}
struct RasterizerVulkan {
    TextureCache texture_cache;
    BufferCache buffer_cache;
    PipelineCache pipeline_cache;
    void UnmapMemory(DAddr,u64);
};
''' + source + r'''
int main() {
    constexpr DAddr never=0x100000, known=0x200000;
    RasterizerVulkan a;
    a.UnmapMemory(never,4096);
    assert(a.texture_cache.mutex.locks==0);
    assert(a.buffer_cache.mutex.locks==0 && a.buffer_cache.writes==0);
    assert(a.pipeline_cache.invalidations==1);
    Eden::BufferPages::Mark(known,4096);
    RasterizerVulkan b;
    b.UnmapMemory(known,4096);
    assert(b.buffer_cache.mutex.locks==1 && b.buffer_cache.writes==1);
    assert(b.pipeline_cache.invalidations==1);
    // A formerly owned buffer must not be optimized away after eviction.
    b.UnmapMemory(known,4096);
    assert(b.buffer_cache.mutex.locks==2 && b.buffer_cache.writes==2);
    // Independent image ownership never forces buffer invalidation.
    Eden::ImagePages::held=true;
    RasterizerVulkan c;
    c.UnmapMemory(never,4096);
    assert(c.texture_cache.mutex.locks==1 && c.texture_cache.unmaps==1);
    assert(c.buffer_cache.mutex.locks==0 && c.buffer_cache.writes==0);
    assert(c.pipeline_cache.invalidations==1);
    Eden::ImagePages::held=false;
    // A large or unknown span MUST retain the original conservative lock.
    RasterizerVulkan d;
    d.UnmapMemory(0x300000,131072);
    assert(d.buffer_cache.mutex.locks==1 && d.buffer_cache.writes==1);
    assert(d.pipeline_cache.invalidations==1);
    Eden::BufferPages::Mark(Eden::BufferPages::kSpace,4096);
    RasterizerVulkan e;
    e.UnmapMemory(never,4096);
    assert(e.buffer_cache.mutex.locks==1 && e.buffer_cache.writes==1);
    assert(e.pipeline_cache.invalidations==1);
}
'''
with tempfile.TemporaryDirectory(prefix="encore-never-owned-unmap-") as tmp:
    src=Path(tmp)/"unit.cpp"
    src.write_text(host)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/opt
        subprocess.run(["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-I",str(root/"headless"),str(src),"-o",str(exe)],check=True,timeout=30)
        subprocess.run([str(exe)],check=True,timeout=10)
        print("NEVER_OWNED_BUFFER_UNMAP_PASS",opt)
