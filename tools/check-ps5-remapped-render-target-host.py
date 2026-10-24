#!/usr/bin/env python3
"""F03/F04: native remapped framebuffer invalidation; source-extracted C++.

Only framebuffer attachments belonging to remapped images should become dirty.
The upstream non-PS5 behavior is unchanged. No console frame trace claimed.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
relative = "src/video_core/texture_cache/texture_cache.h"
src = (ROOT / "vendor/encore-active/eden-backports" / relative).read_text()
native = (ROOT / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
gen = (ROOT / "tools/prepare-vulkan-port.py").read_text()
apply = (ROOT / "tools/apply-eden-backports.sh").read_text()
patch = ROOT / "headless/backports/eden-ps5-texture-remap-target-invalidation.patch"
def body(text):
    a = text.index("void TextureCache<P>::UnmapGPUMemory(")
    return text[a:text.index("\ntemplate <class P>", a)]
method = body(src)
assert body(native) == method, "native Vulkan RT remap method diverged"
assert method in gen, "native generator does not own complete RT remap method"
assert "validate_ps5_texture_remap_target_invalidation" in apply
assert method.count("#ifdef PS5_NATIVE") == 1
for required in ("framebuffer_affected", "Dirty::RenderTargets",
                 "Dirty::ZetaBuffer", "Dirty::ColorBuffer0 + rt",
                 "view_id == NULL_IMAGE_VIEW_ID"):
    assert required in method, required

with tempfile.TemporaryDirectory(prefix="encore-rt-replay-") as folder:
    root=Path(folder)
    target=root / relative
    target.parent.mkdir(parents=True)
    target.write_text(src)
    for cmd in (["git","apply","--reverse","--check",str(patch)],
                ["git","apply","--reverse",str(patch)],
                ["git","apply","--check",str(patch)],
                ["git","apply",str(patch)]):
        result=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=20)
        assert result.returncode==0,(cmd,result.stderr[-3000:])
    assert target.read_text()==src
print("ENCORE_REMAP_FRAMEBUFFER_PATCH_ROUNDTRIP_PASS")

prefix=r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <vector>
#include <boost/container/small_vector.hpp>
using u32=std::uint32_t;
using GPUVAddr=std::uint64_t;
using ImageId=u32;
using ImageViewId=u32;
constexpr ImageViewId NULL_IMAGE_VIEW_ID=0;
constexpr std::size_t NUM_RT=8;
namespace Dirty {
enum :std::size_t {RenderTargets=0,ZetaBuffer=1,ColorBuffer0=2};
}
enum class ImageFlagBits:u32 {CpuModified=1,Tracked=2,Remapped=4};
struct Flags {
    u32 value{};
    bool operator&(ImageFlagBits b) const {return (value & static_cast<u32>(b))!=0;}
    Flags& operator|=(ImageFlagBits b) {value|=static_cast<u32>(b);return *this;}
    Flags& operator&=(u32 mask) {value &= mask; return *this;}
};
bool True(bool b){return b;}
bool False(bool b){return !b;}
struct Image {
    Flags flags{};
    std::vector<ImageViewId> image_view_ids{};
};
struct RendererTargets {
    std::array<ImageViewId,NUM_RT> color_buffer_ids{};
    ImageViewId depth_buffer_id{};
};
struct Maxwell {
    struct State {std::array<bool,64> flags{};} dirty;
};
template<class P>struct TextureCache {
    std::array<Image,12> slot_images{};
    RendererTargets render_targets{};
    Maxwell maxwell{};
    Maxwell* maxwell3d=&maxwell;
    std::vector<ImageId> affected{};
    int untracked=0;
    template<typename F>void ForEachImageInRegionGPU(std::size_t,GPUVAddr,std::size_t,F&& cb) {
        for(const auto id:affected)cb(id,slot_images[id]);
    }
    void UntrackImage(Image& image,ImageId) {
        ++untracked;
        image.flags.value &= ~static_cast<u32>(ImageFlagBits::Tracked);
    }
    void UnmapGPUMemory(std::size_t,GPUVAddr,std::size_t);
};
""" + "\ntemplate<class P>\n" + method + r"""
int main(){
    using Cache=TextureCache<int>;
    Cache rt;
    rt.affected={1};
    rt.slot_images[1].image_view_ids={4,6};
    rt.slot_images[1].flags|=ImageFlagBits::Tracked;
    rt.render_targets.color_buffer_ids[5]=6;
    rt.UnmapGPUMemory(0,0x1000,4096);
    assert(rt.slot_images[1].flags & ImageFlagBits::Remapped);
    assert(rt.slot_images[1].flags & ImageFlagBits::CpuModified);
    assert(rt.untracked==1);
#ifdef PS5_NATIVE
    assert(rt.maxwell.dirty.flags[Dirty::RenderTargets]);
    assert(rt.maxwell.dirty.flags[Dirty::ColorBuffer0+5]);
    assert(!rt.maxwell.dirty.flags[Dirty::ZetaBuffer]);
    for(std::size_t c=0;c<NUM_RT;++c)
        if(c!=5)assert(!rt.maxwell.dirty.flags[Dirty::ColorBuffer0+c]);
#else
    assert(!rt.maxwell.dirty.flags[Dirty::RenderTargets]);
#endif
    Cache depth;
    depth.affected={1};
    depth.slot_images[1].image_view_ids={9};
    depth.render_targets.depth_buffer_id=9;
    depth.UnmapGPUMemory(0,0x2000,1024);
#ifdef PS5_NATIVE
    assert(depth.maxwell.dirty.flags[Dirty::RenderTargets]);
    assert(depth.maxwell.dirty.flags[Dirty::ZetaBuffer]);
    for(std::size_t c=0;c<NUM_RT;++c)
        assert(!depth.maxwell.dirty.flags[Dirty::ColorBuffer0+c]);
#else
    assert(!depth.maxwell.dirty.flags[Dirty::RenderTargets]);
#endif
    Cache unrelated;
    unrelated.affected={1};
    unrelated.slot_images[1].image_view_ids={8};
    unrelated.render_targets.color_buffer_ids[0]=7;
    unrelated.UnmapGPUMemory(0,0x3000,1024);
    assert(!unrelated.maxwell.dirty.flags[Dirty::RenderTargets]);
    Cache null_view;
    null_view.affected={1};
    null_view.slot_images[1].image_view_ids={NULL_IMAGE_VIEW_ID};
    null_view.UnmapGPUMemory(0,0,1);
    assert(!null_view.maxwell.dirty.flags[Dirty::RenderTargets]);
    Cache empty;
    empty.UnmapGPUMemory(0,0,4096);
    assert(!empty.maxwell.dirty.flags[Dirty::RenderTargets]);
}
"""
compilers=list(dict.fromkeys(filter(None,(
    shutil.which("clang++"),shutil.which("g++"),shutil.which("c++")))))
assert compilers, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-remap-rt-host-") as folder:
    cpp=Path(folder)/"rt.cpp"
    cpp.write_text(prefix)
    for compiler in compilers:
        for opt in ("-O0","-O2"):
            for label,flags in (("ps5",["-DPS5_NATIVE"]),("upstream",[])):
                exe=Path(folder)/(Path(compiler).name+opt+label)
                built=subprocess.run(
                    [compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                     "-fsanitize=undefined","-fno-sanitize-recover=all",
                     *flags,str(cpp),"-o",str(exe)],
                    capture_output=True,text=True,timeout=50)
                assert built.returncode==0,(compiler,opt,label,built.stderr[-4000:])
                run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
                assert run.returncode==0,(compiler,opt,label,run.stderr[-4000:])
                print("ENCORE_REMAP_FRAMEBUFFER_PASS",Path(compiler).name,opt,label)
