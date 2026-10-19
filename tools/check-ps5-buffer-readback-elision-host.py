#!/usr/bin/env python3
"""ASan/UBSan actual-method buffer readback mutex elision witness."""
from pathlib import Path
import shutil, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
def read(x):return (root/x).read_text()
raster=read("vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp")
bridge=read("vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp")
pinned=read("vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp")
oracle=read("tools/prepare-vulkan-port.py")
workflow=read(".github/workflows/encore-core-preflight.yml")
buf=read("vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h")
begin="void RasterizerVulkan::FlushRegion(DAddr addr, u64 size, VideoCommon::CacheType which) {"
end="VideoCore::RasterizerDownloadArea RasterizerVulkan::GetFlushArea("
def extract(x):
 assert x.count(begin)==x.count(end)==1
 return x[x.index(begin):x.index(end,x.index(begin))]
body=extract(raster)
assert body==extract(bridge) and body!=extract(pinned)
assert body.count("::Eden::BufferPages::NeverRegistered(addr, size)")==2
assert body.count("::Eden::ImagePages::NeverHeld(addr, size)")==2
assert body.index("buffer_cache.DownloadMemory(addr, size)") < body.index(
 "query_cache.FlushRegion(addr, size)")
assert body.index("buffer_cache.IsRegionGpuModified(addr, size)") < body.index(
 "if (!Settings::IsGPULevelHigh())")
assert '::Eden::BufferPages::Mark(buffer.CpuAddr(), size);' in buf
assert "CPU page registration proof for buffer-only guest readbacks" in oracle
assert "python3 -B tools/check-ps5-buffer-readback-elision-host.py" in workflow
code=r"""
#include <cassert>
#include <cstdint>
#include <mutex>
#include "image_pages.h"
#include "buffer_pages.h"
using DAddr=std::uint64_t;using u64=std::uint64_t;
namespace VideoCommon{enum class CacheType:unsigned {TextureCache=1,BufferCache=2,QueryCache=4};}
constexpr VideoCommon::CacheType operator&(VideoCommon::CacheType a,VideoCommon::CacheType b){
 return static_cast<VideoCommon::CacheType>(static_cast<unsigned>(a)&static_cast<unsigned>(b));
}
constexpr bool True(VideoCommon::CacheType v){return static_cast<unsigned>(v)!=0;}
namespace Settings{inline bool high=true;bool IsGPULevelHigh(){return high;}}
struct Mutex{
 std::recursive_mutex lockable;unsigned counts{};
 void lock(){lockable.lock();++counts;}
 void unlock(){lockable.unlock();}
};
struct Cache{
 Mutex mutex;unsigned downloads{},checks{};bool modified{};
 void DownloadMemory(DAddr,u64){++downloads;}
 bool IsRegionGpuModified(DAddr,u64){++checks;return modified;}
};
struct Query{unsigned calls{};void FlushRegion(DAddr,u64){++calls;}};
class RasterizerVulkan{
public:
 Cache buffer_cache,texture_cache;Query query_cache;
 void FlushRegion(DAddr,u64,VideoCommon::CacheType);
 bool MustFlushRegion(DAddr,u64,VideoCommon::CacheType);
};
__REAL__
int main(){
 using namespace Eden; constexpr u64 p=4096;
 RasterizerVulkan r;
 auto all=static_cast<VideoCommon::CacheType>(7);
 auto b=VideoCommon::CacheType::BufferCache;
 // No buffer registered: query still flushes, buffer mutex is spared.
 r.FlushRegion(10*p,p,all);
 assert(r.buffer_cache.mutex.counts==0 && r.buffer_cache.downloads==0);
 assert(r.texture_cache.mutex.counts==0 && r.query_cache.calls==1);
 // A buffer ever registered retains locked download/probe paths.
 BufferPages::Mark(20*p,p);
 r.FlushRegion(20*p,p,all);
 assert(r.buffer_cache.mutex.counts==1 && r.buffer_cache.downloads==1);
 assert(r.texture_cache.mutex.counts==0 && r.query_cache.calls==2);
 r.FlushRegion(19*p,2*p,b);
 assert(r.buffer_cache.downloads==2 && r.buffer_cache.mutex.counts==2);
 r.FlushRegion(40*p,64*1024+1,b);
 r.FlushRegion(BufferPages::kSpace-2,8,b);
 assert(r.buffer_cache.downloads==4 && r.buffer_cache.mutex.counts==4);
 r.FlushRegion(0,p,all);r.FlushRegion(10*p,0,all);
 assert(r.query_cache.calls==2);
 r.buffer_cache.modified=true;
 assert(!r.MustFlushRegion(30*p,p,b));
 assert(r.buffer_cache.checks==0);
 assert(r.MustFlushRegion(20*p,p,b));
 assert(r.buffer_cache.checks==1);
 assert(r.MustFlushRegion(50*p,0,b)); // unknown zero remains conservative
 assert(r.MustFlushRegion(BufferPages::kSpace,p,b));
 assert(r.buffer_cache.checks==3 && r.buffer_cache.mutex.counts==7);
 // The texture domain is independent of the buffer occupancy map.
 ImagePages::Mark(70*p,p);
 r.texture_cache.modified=true;
 assert(r.MustFlushRegion(70*p,p,all));
 assert(r.buffer_cache.checks==3 && r.texture_cache.checks==1);
 assert(r.texture_cache.mutex.counts==1);
 Settings::high=false;
 assert(!r.MustFlushRegion(70*p,p,all));
 assert(r.texture_cache.checks==1);
}
""".replace("__REAL__",body)
cxx=shutil.which("clang++-18") or shutil.which("clang++")
assert cxx
with tempfile.TemporaryDirectory(prefix="encore-buffer-readback-") as tmp:
 src=Path(tmp)/"test.cpp";exe=Path(tmp)/"test";src.write_text(code)
 subprocess.run([cxx,"-std=c++20","-O1","-pthread","-Wall","-Wextra","-Werror",
                 "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                 "-I"+str(root/"headless"),str(src),"-o",str(exe)],check=True,timeout=55)
 subprocess.run([str(exe)],check=True,timeout=20)
print("VULKAN_BUFFER_READBACK_ELISION_HOST_PASS real_methods=2 no_buffer=1 "
      "registered=1 size_limit=1 zero=1 overflow=1 texture_independent=1 asan_ubsan=1")
