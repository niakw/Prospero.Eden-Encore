#!/usr/bin/env python3
"""F07 P0.4: exercise the source-selected accelerated display candidate filter.

GPU-authored clean frames may be sampled directly; CPU-dirtied or remapped
images must not expose retired Vulkan pixels and must take the existing guest
framebuffer upload path. This is a real source-extracted host predicate, NOT
a PS5 image or swapchain content validation.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cache = (root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator = (root/"tools/prepare-vulkan-port.py").read_text()
raster = (root/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
layer = (root/"vendor/encore-active/eden-vulkan/vulkan_present_layer.cpp").read_text()
fast = (root/".github/workflows/encore-core-fast-gate.yml").read_text()
full = (root/".github/workflows/encore-core-preflight.yml").read_text()

sig = "TextureCache<P>::TryFindFramebufferImageView("
assert cache.count(sig) == 1
method = cache.split(sig,1)[1].split("\ntemplate <class P>",1)[0]
start = "    for (const ImageMapId map_id : image_map_ids) {"
stop = "\n\n    const auto view_format ="
assert method.count(start) == 1
loop = method[method.index(start):method.index(stop,method.index(start))]
assert loop.count("ImageFlagBits::Remapped | ImageFlagBits::CpuModified") == 1
assert loop.count("if (True(image.flags & ImageFlagBits::IsDecoding)) {") == 1
assert loop.index("if (True(image.flags & ImageFlagBits::IsDecoding)) {") < loop.index("ImageFlagBits::Remapped | ImageFlagBits::CpuModified")
assert "return {};" in loop
assert loop.index("if (image.cpu_addr != cpu_addr)") < loop.index("ImageFlagBits::Remapped | ImageFlagBits::CpuModified")
assert loop.index("ImageFlagBits::Remapped | ImageFlagBits::CpuModified") < loop.index("if (image.image_view_ids.empty())")
assert "F07 P0.4 accelerated present rejects remapped or CPU-dirty framebuffer" in generator
assert "F07 P0.4 exclude asynchronously decoding accelerated framebuffer" in generator
assert "F07 P0.4 prevent stale alternate framebuffer view during async decode" in generator
display = raster.split("RasterizerVulkan::AccelerateDisplay(",1)[1].split("return info;",1)[0]
assert "if (!image_view) {" in display
assert display.count("gpu_memory->FlushCaching();") == 1
assert display.index("gpu_memory->FlushCaching();") < display.index("std::scoped_lock lock{texture_cache.mutex};")
assert display.index("std::scoped_lock lock{texture_cache.mutex};") < display.index("TryFindFramebufferImageView(config, framebuffer_addr)")
assert "F07 P0.4 present flushes remaps before inspecting image cache" in generator
# The engine's regular DrawTexture path provides a proven ownership/locking
# pattern for this extra present-side flush.
draw_texture=raster.split("void RasterizerVulkan::DrawTexture() {",1)[1].split("void RasterizerVulkan::Clear(",1)[0]
assert draw_texture.index("gpu_memory->FlushCaching();") < draw_texture.index("std::scoped_lock l{texture_cache.mutex};")
assert "return {};" in raster.split("RasterizerVulkan::AccelerateDisplay(",1)[1].split("query_cache.NotifySegment",1)[0]
assert "if (!use_accelerated) {\n        UpdateRawImage(framebuffer, image_index);" in layer
for wf in (fast,full):
    assert "python3 -B tools/check-ps5-present-framebuffer-freshness-host.py" in wf

cpp=r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <unordered_map>
#include <vector>
using DAddr = std::uint64_t;
using ImageId = int;
using ImageMapId = int;
namespace boost::container {
template<class T,std::size_t N> using small_vector = std::vector<T>;
}
enum class ImageFlagBits : unsigned { Remapped=1u, CpuModified=2u, IsDecoding=4u };
constexpr unsigned operator|(ImageFlagBits a,ImageFlagBits b) {
    return static_cast<unsigned>(a)|static_cast<unsigned>(b);
}
constexpr unsigned operator|(unsigned a,ImageFlagBits b) {
    return a|static_cast<unsigned>(b);
}
constexpr unsigned operator&(unsigned a,ImageFlagBits b) {
    return a&static_cast<unsigned>(b);
}
bool True(unsigned flags) { return flags != 0; }
struct ImageMapView { int image_id{}; };
struct ImageBase {
    DAddr cpu_addr{};
    unsigned flags{};
    std::vector<int> image_view_ids;
};
struct Selector {
    std::unordered_map<int,ImageMapView> slot_map_views;
    std::unordered_map<int,ImageBase> slot_images;
    std::vector<ImageMapId> image_map_ids;
    std::vector<ImageId> Run(DAddr cpu_addr) {
        boost::container::small_vector<ImageId,4> valid_image_ids;
__SOURCE_LOOP__
        return valid_image_ids;
    }
};
int main() {
    Selector c;
    constexpr DAddr guest = 0x9000;
    for(int i=1;i<=7;++i) {
        c.slot_map_views[i]={i};
        c.slot_images[i]={guest,0,{i}};
        c.image_map_ids.push_back(i);
    }
    c.slot_images[2].flags=static_cast<unsigned>(ImageFlagBits::CpuModified);
    c.slot_images[3].flags=static_cast<unsigned>(ImageFlagBits::Remapped);
    c.slot_images[4].image_view_ids.clear();
    c.slot_images[5].cpu_addr=guest+4096;
    c.slot_images[7].flags=ImageFlagBits::Remapped|ImageFlagBits::CpuModified;
    // The old GPU view is stale while the fresh guest bytes are decoding.
    c.slot_images[6].flags=static_cast<unsigned>(ImageFlagBits::IsDecoding);
    // The clean image precedes the decoding view: selecting it is stale.
    const auto clean=c.Run(guest);
    assert(clean.empty());
    // Likewise when an in-flight decode appears before the clean image.
    c.image_map_ids={6,1,2,3,4,5,7};
    assert(c.Run(guest).empty());
    c.image_map_ids={1,2,3,4,5,6,7};
    c.slot_images[1].flags=static_cast<unsigned>(ImageFlagBits::Remapped);
    c.slot_images[6].flags=static_cast<unsigned>(ImageFlagBits::CpuModified);
    assert(c.Run(guest).empty());
    // Guest update/reupload has completed; clean GPU images may accelerate again.
    c.slot_images[2].flags=0;
    c.slot_images[3].flags=0;
    const auto restored=c.Run(guest);
    assert((restored==std::vector<int>{2,3}));
    c.slot_images[6].flags=0; // Async decode finished; acceleration is safe again.
    assert((c.Run(guest)==std::vector<int>{2,3,6}));
}
'''.replace("__SOURCE_LOOP__",loop)
with tempfile.TemporaryDirectory(prefix="encore-f07-present-fresh-") as d:
    src=Path(d)/"fresh.cpp"
    src.write_text(cpp)
    for optimization in ("-O0","-O2"):
        out=Path(d)/optimization
        subprocess.run(["c++","-std=c++20",optimization,"-DPS5_NATIVE",
                        "-Wall","-Wextra","-Werror",str(src),"-o",str(out)],check=True,timeout=60)
        subprocess.run([str(out)],check=True,timeout=15)
        print("F07_PRESENT_FRAMEBUFFER_FRESHNESS_PASS",optimization)
