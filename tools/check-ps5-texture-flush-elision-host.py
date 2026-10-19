#!/usr/bin/env python3
"""Sanitized source-extracted C++ test of no-image texture readback elision."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
def read(p): return (root/p).read_text()
raster=read("vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp")
bridge=read("vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp")
pinned=read("vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp")
oracle=read("tools/prepare-vulkan-port.py")
workflow=read(".github/workflows/encore-core-preflight.yml")
cache=read("vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h")
start="void RasterizerVulkan::FlushRegion(DAddr addr, u64 size, VideoCommon::CacheType which) {"
end="VideoCore::RasterizerDownloadArea RasterizerVulkan::GetFlushArea("
def extract(s):
    assert s.count(start)==s.count(end)==1
    return s[s.index(start):s.index(end,s.index(start))]
body=extract(raster)
assert body==extract(bridge) and body!=extract(pinned)
assert body.count("::Eden::ImagePages::NeverHeld(addr, size)")==2
assert "size == 0 || !::Eden::ImagePages::NeverHeld(addr, size)" in body
assert body.index("buffer_cache.IsRegionGpuModified(addr, size)") < body.index(
       "if (!Settings::IsGPULevelHigh())")
assert "buffer_cache.DownloadMemory(addr, size)" in body
assert "query_cache.FlushRegion(addr, size)" in body
assert cache.index("::Eden::ImagePages::Mark(image.cpu_addr") < cache.index(
       "slot_map_views.insert(image.gpu_addr")
assert cache.index("::Eden::ImagePages::Mark(cpu_addr, size)") < cache.index(
       "slot_map_views.insert(gpu_addr, cpu_addr")
assert "Skip impossible texture readback mutex acquisitions" in oracle
assert "python3 -B tools/check-ps5-texture-flush-elision-host.py" in workflow
cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include "image_pages.h"
using DAddr=std::uint64_t;
using u64=std::uint64_t;
namespace VideoCommon {enum class CacheType: unsigned {TextureCache=1,BufferCache=2,QueryCache=4};}
constexpr VideoCommon::CacheType operator&(VideoCommon::CacheType a,VideoCommon::CacheType b){
 return static_cast<VideoCommon::CacheType>(static_cast<unsigned>(a)&static_cast<unsigned>(b));
}
constexpr bool True(VideoCommon::CacheType x){return static_cast<unsigned>(x)!=0;}
namespace Settings {inline bool high=true; bool IsGPULevelHigh(){return high;}}
struct Mutex{
 std::recursive_mutex impl;
 unsigned calls{};
 void lock(){impl.lock();++calls;}
 void unlock(){impl.unlock();}
};
struct Cache{
 Mutex mutex;
 unsigned downloads{},probes{};
 bool gpu_modified=false;
 void DownloadMemory(DAddr,u64){++downloads;}
 bool IsRegionGpuModified(DAddr,u64){++probes;return gpu_modified;}
};
struct Query{
 unsigned calls{};
 void FlushRegion(DAddr,u64){++calls;}
};
class RasterizerVulkan{
public:
 Cache buffer_cache,texture_cache;
 Query query_cache;
 void FlushRegion(DAddr,u64,VideoCommon::CacheType);
 bool MustFlushRegion(DAddr,u64,VideoCommon::CacheType);
};
__BODY__
int main(){
 constexpr DAddr p=4096;
 RasterizerVulkan x;
 auto all=static_cast<VideoCommon::CacheType>(7);
 auto tex=VideoCommon::CacheType::TextureCache;
 x.FlushRegion(10*p,p,all);
 assert(x.texture_cache.mutex.calls==0 && x.texture_cache.downloads==0);
 assert(x.buffer_cache.downloads==1 && x.query_cache.calls==1);
 x.FlushRegion(0,p,all);x.FlushRegion(10*p,0,all);
 assert(x.buffer_cache.downloads==1 && x.query_cache.calls==1);
 Eden::ImagePages::Mark(20*p,p);
 x.FlushRegion(20*p,p,all);x.FlushRegion(19*p,2*p,tex);
 assert(x.texture_cache.mutex.calls==2 && x.texture_cache.downloads==2);
 assert(x.buffer_cache.downloads==2 && x.query_cache.calls==2);
 x.FlushRegion(30*p,256*1024+1,tex);
 x.FlushRegion(Eden::ImagePages::kSpace-1,8,tex);
 assert(x.texture_cache.mutex.calls==4 && x.texture_cache.downloads==4);
 x.texture_cache.gpu_modified=true;
 assert(!x.MustFlushRegion(50*p,p,tex));
 assert(x.texture_cache.probes==0 && x.texture_cache.mutex.calls==4);
 assert(x.MustFlushRegion(20*p,p,tex));
 assert(x.texture_cache.probes==1 && x.texture_cache.mutex.calls==5);
 assert(x.MustFlushRegion(40*p,256*1024+1,tex));
 assert(x.MustFlushRegion(Eden::ImagePages::kSpace,8,tex));
 assert(x.texture_cache.probes==3 && x.texture_cache.mutex.calls==7);
 assert(x.MustFlushRegion(50*p,0,tex));
 assert(x.texture_cache.probes==4 && x.texture_cache.mutex.calls==8);
 Settings::high=false;
 assert(!x.MustFlushRegion(20*p,p,tex));
 assert(x.texture_cache.probes==4);
 Settings::high=true;
 x.buffer_cache.gpu_modified=true;
 assert(x.MustFlushRegion(50*p,p,all));
 assert(x.buffer_cache.probes==1 && x.texture_cache.probes==4);
 x.buffer_cache.gpu_modified=false;
 assert(!x.MustFlushRegion(50*p,p,all));
 assert(x.buffer_cache.probes==2 && x.texture_cache.probes==4);
}
""".replace("__BODY__",body)
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-flush-") as tmp:
 src=Path(tmp)/"test.cpp";exe=Path(tmp)/"test"
 src.write_text(cpp)
 subprocess.run([compiler,"-std=c++20","-O1","-pthread","-Wall","-Wextra","-Werror",
                 "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                 "-I"+str(root/"headless"),str(src),"-o",str(exe)],check=True,timeout=55)
 subprocess.run([str(exe)],check=True,timeout=20)
print("VULKAN_TEXTURE_FLUSH_ELISION_HOST_PASS actual_methods=2 readback=1 buffer=1 "
      "query=1 zero_size=1 range_guard=1 high_mode=1 asan_ubsan=1")
