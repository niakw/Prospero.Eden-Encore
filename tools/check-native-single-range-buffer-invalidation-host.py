#!/usr/bin/env python3
"""Compile selected native single-range GPU invalidation methods and test lock elision."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
def take(begin, end):
    return src[src.index(begin):src.index(end, src.index(begin))]
inv = take("void RasterizerVulkan::InvalidateRegion(", "void RasterizerVulkan::InnerInvalidation(")
cache = take("void RasterizerVulkan::OnCacheInvalidation(", "void RasterizerVulkan::InvalidateGPUCache()")
assert inv.count("::Eden::BufferPages::NeverRegistered(addr, size)") == 1
assert cache.count("::Eden::BufferPages::NeverRegistered(addr, size)") == 1
assert inv.index("texture_cache.WriteMemory") < inv.index("buffer_cache.WriteMemory") < inv.index("query_cache.InvalidateRegion") < inv.index("pipeline_cache.InvalidateRegion")
assert cache.index("texture_cache.WriteMemory") < cache.index("buffer_cache.WriteMemory") < cache.index("pipeline_cache.InvalidateRegion")
cmake = (root / "headless/vulkan.cmake").read_text()
assert 'file(COPY "${EDEN_ACTIVE_VULKAN}/" DESTINATION "${PORT_BUILD_DIR}")' in cmake
assert '"${PORT_BUILD_DIR}/vulkan_rasterizer.cpp"' in cmake
generator = (root / "tools/prepare-vulkan-port.py").read_text()
assert "future buffer" in generator or "their first upload is unaffected" in generator
buffer_owner = (root / "vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
reg = buffer_owner[buffer_owner.index("void BufferCache<P>::ChangeRegister("):]
assert reg.index("::Eden::BufferPages::Mark(buffer.CpuAddr(), size);") < reg.index("page_table[page] = buffer_id;")
word_owner = (root / "vendor/sources/eden/src/video_core/buffer_cache/word_manager.h").read_text()
assert "std::fill_n(heap.data() + size_t(Type::CPU) * num_words, num_words, ~u64{0});" in word_owner
host = r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <vector>
#include <utility>
#include "buffer_pages.h"
using DAddr = std::uint64_t;
using u64 = std::uint64_t;
namespace VideoCommon {
enum class CacheType: unsigned {
    BufferCache=1u, TextureCache=2u, QueryCache=4u, ShaderCache=8u
};
inline CacheType operator&(CacheType a, CacheType b) {
    return static_cast<CacheType>(static_cast<unsigned>(a)&static_cast<unsigned>(b));
}
}
inline bool True(VideoCommon::CacheType type) {
    return static_cast<unsigned>(type) != 0;
}
namespace Eden::ImagePages {
inline bool held = false;
inline bool NeverHeld(u64, u64) { return !held; }
}
struct CountMutex {
    std::mutex impl;
    unsigned locks = 0;
    void lock() { impl.lock(); ++locks; }
    void unlock() { impl.unlock(); }
};
struct Cache {
    CountMutex mutex;
    std::vector<std::pair<DAddr,u64>> written;
    void WriteMemory(DAddr a, u64 sz) { written.emplace_back(a,sz); }
};
struct Owner {
    unsigned calls=0;
    void InvalidateRegion(DAddr, u64) { ++calls; }
};
struct RasterizerVulkan {
    Cache texture_cache, buffer_cache;
    Owner query_cache, pipeline_cache;
    void InvalidateRegion(DAddr, u64, VideoCommon::CacheType);
    void OnCacheInvalidation(DAddr, u64);
};
''' + inv + cache + r'''
int main() {
    using VideoCommon::CacheType;
    using V = VideoCommon::CacheType;
    constexpr auto full = static_cast<V>(15);
    constexpr DAddr blank = 0x100000, prior = 0x200000;
    RasterizerVulkan empty;
    empty.InvalidateRegion(blank, 4096, full);
    assert(empty.buffer_cache.mutex.locks==0 && empty.buffer_cache.written.empty());
    assert(empty.texture_cache.mutex.locks==0);
    assert(empty.query_cache.calls==1 && empty.pipeline_cache.calls==1);
    empty.OnCacheInvalidation(blank,4096);
    assert(empty.buffer_cache.mutex.locks==0);
    assert(empty.pipeline_cache.calls==2);
    empty.InvalidateRegion(0,4096,full);
    empty.OnCacheInvalidation(blank,0);
    assert(empty.query_cache.calls==1 && empty.pipeline_cache.calls==2);
    // Existing or formerly-owned buffers must always take the lock.
    Eden::BufferPages::Mark(prior,4096);
    RasterizerVulkan known;
    known.InvalidateRegion(prior,4096,full);
    known.OnCacheInvalidation(prior,4096);
    assert(known.buffer_cache.mutex.locks==2 && known.buffer_cache.written.size()==2);
    assert(known.query_cache.calls==1 && known.pipeline_cache.calls==2);
    // Texture-only image ownership must not force buffer-cache work.
    Eden::ImagePages::held=true;
    RasterizerVulkan image;
    image.InvalidateRegion(blank,4096,full);
    image.OnCacheInvalidation(blank,4096);
    assert(image.texture_cache.written.size()==2);
    assert(image.buffer_cache.written.empty());
    assert(image.pipeline_cache.calls==2);
    Eden::ImagePages::held=false;
    // Unknown spans are conservative. NeverRegistered must fail closed.
    RasterizerVulkan large;
    large.InvalidateRegion(0x300000,131072,full);
    large.OnCacheInvalidation(0x300000,131072);
    assert(large.buffer_cache.mutex.locks==2);
    // Cache mask is respected: no unintended buffer invalidation.
    RasterizerVulkan isolated;
    isolated.InvalidateRegion(prior,4096,CacheType::ShaderCache);
    assert(isolated.buffer_cache.mutex.locks==0 && isolated.pipeline_cache.calls==1);
    // Unknown monotonic coverage forces the pre-existing buffer lock path.
    Eden::BufferPages::Mark(Eden::BufferPages::kSpace,4096);
    RasterizerVulkan unknown;
    unknown.InvalidateRegion(blank,4096,full);
    unknown.OnCacheInvalidation(blank,4096);
    assert(unknown.buffer_cache.mutex.locks==2);
    assert(unknown.query_cache.calls==1 && unknown.pipeline_cache.calls==2);
}
'''
with tempfile.TemporaryDirectory(prefix="encore-unit-buffer-") as tmp:
    cpp = Path(tmp)/"main.cpp"
    cpp.write_text(host)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/("fixture"+opt)
        subprocess.run(["c++","-std=c++20",opt,"-pthread","-Wall","-Wextra","-Werror",
                        "-I",str(root/"headless"),str(cpp),"-o",str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
        print("NATIVE_SINGLE_RANGE_BUFFER_INVALIDATION_PASS",opt)
