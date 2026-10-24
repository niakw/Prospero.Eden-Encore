#!/usr/bin/env python3
"""F04: source-selected TIC view bounds, missing layers and native patch replay."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/video_core/texture_cache/texture_cache.h").read_text()
shipping = (root / "vendor/encore-active/eden-backports/src/video_core/texture_cache/texture_cache.h").read_text()
native = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
installer = (root / "tools/apply-eden-backports.sh").read_text()
patch = root / "headless/backports/eden-ps5-texture-tic-layer-bounds.patch"
cmake = (root / "headless/vulkan.cmake").read_text()
assert "vulkan-cache" in cmake and "target_include_directories(video_core BEFORE PUBLIC" in cmake
assert 'apply_one "$root/headless/backports/eden-ps5-texture-tic-layer-bounds.patch"' in installer
assert "F04 native TIC layer view safety" in generator

def method(source: str) -> str:
    start = source.index("ImageViewId TextureCache<P>::CreateImageView(")
    return source[start:source.index("\ntemplate <class P>", start)]

selected = method(shipping)
assert method(native) == selected, "shipping/native TIC view logic drift"
assert selected in generator, "generator does not reconstruct selected native method"
assert selected.count("#ifdef PS5_NATIVE") == 2
assert selected.count("static_cast<u64>(config.BaseLayer()) * info.layer_stride") == 1
assert selected.index("if (layer_offset > config.Address())") < selected.index(
    "FindOrInsertImage(info, image_gpu_addr)")
assert selected.index("if (!base)") < selected.index("FindOrEmplaceImageView(image_id, view_info)")
assert selected.count("const SubresourceBase base = image.TryFindBase(config.Address()).value();") == 1

# The TIC patch is intentionally relative to the maintained shipping
# source, not the pristine upstream archive: earlier reviewed backports
# changed surrounding function context. Remove this ordered F04 stack,
# then apply the TIC patch against its actual pre-F04 source.
patch_stack = (
    patch,
    root / "headless/backports/eden-ps5-texture-remapped-view-rebind.patch",
    root / "headless/backports/eden-ps5-texture-remap-target-invalidation.patch",
    root / "headless/backports/eden-ps5-texture-missing-channel-slot-guard.patch",
)
with tempfile.TemporaryDirectory(prefix="encore-tic-patch-") as tmp:
    stage = Path(tmp)
    target = stage / "src/video_core/texture_cache/texture_cache.h"
    target.parent.mkdir(parents=True)
    target.write_text(shipping)
    for later in reversed(patch_stack):
        for args in (["--reverse", "--check", str(later)],
                     ["--reverse", str(later)]):
            command = ["git", "apply", *args]
            run = subprocess.run(command, cwd=stage, text=True,
                                 capture_output=True, timeout=20)
            assert run.returncode == 0, (command, run.stderr[-3000:])
    assert method(target.read_text()) == method(pinned), "pre-F04 TIC logic drift"
    for args in (["--check", str(patch)], [str(patch)]):
        command = ["git", "apply", *args]
        run = subprocess.run(command, cwd=stage, text=True,
                             capture_output=True, timeout=20)
        assert run.returncode == 0, (command, run.stderr[-3000:])
    assert method(target.read_text()) == selected
print("ENCORE_F04_TIC_ORDERED_PATCH_REPLAY_PASS")

fixture = r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <optional>
using u32=std::uint32_t;
using u64=std::uint64_t;
using GPUVAddr=u64;
using ImageId=u32;
using ImageViewId=u32;
constexpr ImageViewId NULL_IMAGE_VIEW_ID=0;
#define ASSERT(x) assert(x)
enum class ImageType { Buffer, Texture };
enum class ImageViewFlagBits : u32 { Strong=1 };
enum class ImageFlagBits : u32 { Strong=1 };
struct Flags {
    u32 val{};
    template<class T> Flags& operator|=(T x) {val|=static_cast<u32>(x);return *this;}
};
struct TICEntry {
    GPUVAddr address{};
    u32 layer{};
    u32 stride{};
    ImageType type=ImageType::Texture;
    GPUVAddr Address() const {return address;}
    u32 BaseLayer() const {return layer;}
};
struct ImageInfo {
    ImageType type;
    u32 layer_stride{};
    explicit ImageInfo(const TICEntry& tic):type(tic.type),layer_stride(tic.stride){}
};
struct ImageViewInfo {
    u32 layer{};
    ImageViewInfo(const TICEntry&,u32 x):layer(x){}
};
struct SubresourceBase {u32 level{},layer{};};
struct ImageBase {
    Flags flags{};
    bool mapped=true;
    std::optional<SubresourceBase> TryFindBase(GPUVAddr) const {
        if(!mapped)return std::nullopt;
        return SubresourceBase{0,4};
    }
};
struct ImageViewBase {Flags flags{};};
struct Runtime {};
struct ViewTable {
    std::array<ImageViewBase,8> items{};
    int inserts{};
    ImageViewId insert(Runtime&,const ImageInfo&,const ImageViewInfo&,GPUVAddr) {
        ++inserts;return 3;
    }
    ImageViewBase& operator[](ImageViewId id) {return items.at(id);}
};
template<class P> struct TextureCache {
    Runtime runtime{};
    ViewTable slot_image_views{};
    std::array<ImageBase,8> slot_images{};
    bool allow_image=true;
    GPUVAddr last_gpu_addr{};
    int find_calls{};
    ImageId FindOrInsertImage(const ImageInfo&,GPUVAddr a) {
        ++find_calls;
        last_gpu_addr=a;
        return allow_image?1:0;
    }
    ImageViewId FindOrEmplaceImageView(ImageId id,const ImageViewInfo&) {
        assert(id==1);return 2;
    }
    ImageViewId CreateImageView(const TICEntry& config);
};
""" + "\ntemplate<class P>\n" + selected + r"""
int main() {
    TextureCache<int> cache;
    const TICEntry normal{0x20000,2,0x1000,ImageType::Texture};
    assert(cache.CreateImageView(normal)==2);
    assert(cache.last_gpu_addr==0x1e000);
    assert(cache.slot_images[1].flags.val==1);
    assert(cache.slot_image_views[2].flags.val==1);
    const TICEntry buffer{0x30000,0,0,ImageType::Buffer};
    const int before=cache.find_calls;
    assert(cache.CreateImageView(buffer)==3 && cache.find_calls==before);
    // 65536 * 65536 = 4 GiB: upstream used to truncate the layer offset.
    const TICEntry huge{0x400001000ULL,65536,65536,ImageType::Texture};
    assert(cache.CreateImageView(huge)==2);
#ifdef PS5_NATIVE
    assert(cache.last_gpu_addr==0x300001000ULL);
#else
    assert(cache.last_gpu_addr==0x400001000ULL);
#endif
    cache.allow_image=false;
    assert(cache.CreateImageView(normal)==NULL_IMAGE_VIEW_ID);
    cache.allow_image=true;
#ifdef PS5_NATIVE
    const int called=cache.find_calls;
    assert(cache.CreateImageView({0x1000,2,0x1000,ImageType::Texture})
           ==NULL_IMAGE_VIEW_ID);
    assert(cache.find_calls==called);
    cache.slot_images[1].mapped=false;
    assert(cache.CreateImageView(normal)==NULL_IMAGE_VIEW_ID);
    cache.slot_images[1].mapped=true;
    assert(cache.CreateImageView(normal)==2);
#endif
}
"""
compilers=list(dict.fromkeys(filter(None,(
    shutil.which("clang++"),shutil.which("g++"),shutil.which("c++")))))
assert compilers, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-tic-host-") as tmp:
    cpp=Path(tmp)/"tic.cpp"
    cpp.write_text(fixture)
    for compiler in compilers:
        for opt in ("-O0","-O2"):
            for label, defines in (("ps5",["-DPS5_NATIVE"]),("upstream",[])):
                exe=Path(tmp)/(Path(compiler).name+opt+label)
                built=subprocess.run(
                    [compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                     "-fsanitize=undefined","-fno-sanitize-recover=all",
                     *defines,str(cpp),"-o",str(exe)],
                    capture_output=True,text=True,timeout=50)
                assert built.returncode==0,(compiler,opt,label,built.stderr[-5000:])
                ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
                assert ran.returncode==0,(compiler,opt,label,ran.stderr[-5000:])
                print("ENCORE_F04_TIC_LAYER_PASS",Path(compiler).name,opt,label)
