#!/usr/bin/env python3
"""Source-extracted ASan/UBSan: absent guest backing cannot upload stale staging."""
from pathlib import Path
import subprocess, shutil, tempfile
ROOT=Path(__file__).resolve().parents[1]
active=(ROOT/"vendor/encore-active/eden-vulkan/vulkan_present_layer.cpp").read_text()
pinned=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/present/layer.cpp").read_text()
generator=(ROOT/"tools/prepare-vulkan-port.py").read_text()
ci=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-vulkan-present-missing-guest-host.py" in ci
assert "Never upload recycled staging bytes" in generator
assert "std::fill(linear_span.begin(), linear_span.end(), u8{0});" in active
start="    if (host_ptr) {"
stop="\n\n    const VkBufferImageCopy copy{"
new_start="    const std::span<u8> linear_span = mapped_span.subspan(image_offset, linear_size);"
assert active.count(start)==1 and pinned.count(start)==1 and active.count(new_start)==1
old=pinned[pinned.index(start):pinned.index(stop,pinned.index(start))]
new=active[active.index(new_start):active.index(stop,active.index(new_start))]
cpp=r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <span>
#include <vector>
using u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;
struct Framebuffer{u32 width=2,height=2;};
struct Buffer{unsigned flushes=0;void Flush(){++flushes;}};
static unsigned unswizzles=0;
namespace Tegra::Texture{
void UnswizzleTexture(std::span<u8> dst,std::span<const u8> src,u32,u32,u32,u32,u32,u32){
    ++unswizzles;assert(src.size()>=dst.size());
    std::copy_n(src.begin(),dst.size(),dst.begin());
}
}
void RunOld(std::span<u8> mapped_span,u64 image_offset,u64 linear_size,
            const u8* host_ptr,u64 tiled_size,u32 bytes_per_pixel,
            Framebuffer framebuffer,Buffer& buffer){
    constexpr u32 block_height_log2=4;
INJECT_OLD
}
void RunNew(std::span<u8> mapped_span,u64 image_offset,u64 linear_size,
            const u8* host_ptr,u64 tiled_size,u32 bytes_per_pixel,
            Framebuffer framebuffer,Buffer& buffer){
    constexpr u32 block_height_log2=4;
INJECT_NEW
}
int main(){
    std::vector<u8> pixels(12,0xAB);
    Buffer baseline;RunOld(pixels,4,4,nullptr,4,1,{},baseline);
    assert(baseline.flushes==0 && unswizzles==0);
    assert(std::all_of(pixels.begin(),pixels.end(),[](u8 x){return x==0xAB;}));
    Buffer corrected;RunNew(pixels,4,4,nullptr,4,1,{},corrected);
    assert(corrected.flushes==1 && unswizzles==0);
    for(size_t i=0;i<pixels.size();++i)
        assert(pixels[i]==(i>=4&&i<8?0:0xAB));
    const u8 fresh[]={1,2,3,4};
    RunNew(pixels,4,4,fresh,4,1,{},corrected);
    assert(corrected.flushes==2 && unswizzles==1);
    for(size_t i=0;i<4;++i)assert(pixels[i+4]==fresh[i]);
    assert(pixels.front()==0xAB && pixels.back()==0xAB);
    std::puts("ENCORE_STALE_STAGE_CLEAR_PASS");
}
""".replace("INJECT_OLD",old).replace("INJECT_NEW",new)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-layer-stale-") as folder:
    src=Path(folder)/"layer.cpp";exe=Path(folder)/"layer";src.write_text(cpp)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(src),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("HOST_VULKAN_STALE_STAGING_CLEAR_PASS; device and FPS unmeasured")
