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
declare_anchor = "    const auto& image_map_ids = it->second;\n"
assert method.count(declare_anchor) == 1
declaration = method[method.index(declare_anchor)+len(declare_anchor):method.index(start)]
selection_anchor = "\n#ifdef PS5_NATIVE\n    if (freshest_found)"
assert method.count(selection_anchor) == 1
selection = method[method.index(selection_anchor)+1:method.rindex("\n}")]
assert "ImageId freshest_id{};" in declaration
assert "bool freshest_found = false;" in declaration
assert "#else\n    boost::container::small_vector<ImageId, 4> valid_image_ids;" in declaration
assert loop.count("if (True(image.flags & ImageFlagBits::IsDecoding)) {") == 1
assert loop.count("ImageFlagBits::Remapped | ImageFlagBits::CpuModified") == 1
assert "return {};" in loop
assert loop.count("if (!freshest_found ||") == 1
assert loop.count("slot_images[freshest_id].modification_tick < image.modification_tick") == 1
assert loop.index("if (image.cpu_addr != cpu_addr)") < loop.index("ImageFlagBits::IsDecoding")
assert loop.index("ImageFlagBits::IsDecoding") < loop.index("if (image.image_view_ids.empty())")
assert "valid_image_ids.push_back(map.image_id);" in loop
assert "return GetImageViewForFramebuffer(freshest_id);" in selection
assert "std::ranges::max_element(valid_image_ids" in selection  # desktop untouched
for label in (
    "F07 P0.4 accelerated present rejects remapped or CPU-dirty framebuffer",
    "F07 P0.4 exclude asynchronously decoding accelerated framebuffer",
    "F07 P0.4 prevent stale alternate framebuffer view during async decode",
    "F07 P0.4 framebuffer single-pass candidate declaration",
    "F07 P0.4 framebuffer single-pass admission",
    "F07 P0.4 framebuffer single-pass first-tie selection",
):
    assert label in generator
display = raster.split("RasterizerVulkan::AccelerateDisplay(",1)[1].split("return info;",1)[0]
assert "if (!image_view) {" in display
assert display.count("gpu_memory->FlushCaching();") == 1
assert display.index("gpu_memory->FlushCaching();") < display.index("std::scoped_lock lock{texture_cache.mutex};")
assert display.index("std::scoped_lock lock{texture_cache.mutex};") < display.index("TryFindFramebufferImageView(config, framebuffer_addr)")
assert "F07 P0.4 present flushes remaps before inspecting image cache" in generator
draw_texture=raster.split("void RasterizerVulkan::DrawTexture() {",1)[1].split("void RasterizerVulkan::Clear(",1)[0]
assert draw_texture.index("gpu_memory->FlushCaching();") < draw_texture.index("std::scoped_lock l{texture_cache.mutex};")
assert "return {};" in raster.split("RasterizerVulkan::AccelerateDisplay(",1)[1].split("query_cache.NotifySegment",1)[0]
assert "if (!use_accelerated) {\n        UpdateRawImage(framebuffer, image_index);" in layer
for wf in (fast,full):
    assert "python3 -B tools/check-ps5-present-framebuffer-freshness-host.py" in wf

cpp=r'''
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <ranges>
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
constexpr unsigned operator&(unsigned a,ImageFlagBits b) {
    return a&static_cast<unsigned>(b);
}
bool True(unsigned flags) { return flags != 0; }
struct ImageMapView { int image_id{}; };
struct ImageBase {
    DAddr cpu_addr{};
    unsigned flags{};
    std::vector<int> image_view_ids;
    std::uint64_t modification_tick{};
};
struct Selector {
    std::unordered_map<int,ImageMapView> slot_map_views;
    std::unordered_map<int,ImageBase> slot_images;
    std::vector<ImageMapId> image_map_ids;
    std::vector<ImageId> Run(DAddr cpu_addr) {
        const auto& image_map_ids = this->image_map_ids;
__SOURCE_DECLARE__
__SOURCE_LOOP__
        auto GetImageViewForFramebuffer = [](ImageId id) {
            return std::vector<ImageId>{id};
        };
__SOURCE_SELECT__
    }
};
int main() {
    Selector c;
    constexpr DAddr guest = 0x9000;
    for(int i=1;i<=8;++i) {
        c.slot_map_views[i]={i};
        c.slot_images[i]={guest,0,{i},static_cast<std::uint64_t>(i)};
        c.image_map_ids.push_back(i);
    }
    c.slot_images[8].cpu_addr=guest+4096;
    c.slot_images[2].flags=static_cast<unsigned>(ImageFlagBits::CpuModified);
    c.slot_images[3].flags=static_cast<unsigned>(ImageFlagBits::Remapped);
    c.slot_images[4].image_view_ids.clear();
    c.slot_images[7].flags=ImageFlagBits::Remapped|ImageFlagBits::CpuModified;
    c.slot_images[6].flags=static_cast<unsigned>(ImageFlagBits::IsDecoding);
    // A clean candidate precedes a decoding view: do NOT present it.
    assert(c.Run(guest).empty());
    c.image_map_ids={6,1,2,3,4,5,7,8};
    assert(c.Run(guest).empty());
    c.image_map_ids={1,2,3,4,5,6,7,8};
    // No decode, but the dirty/empty views must be excluded.
    c.slot_images[6].flags=static_cast<unsigned>(ImageFlagBits::CpuModified);
    assert((c.Run(guest)==std::vector<int>{5}));
    c.slot_images[1].flags=static_cast<unsigned>(ImageFlagBits::Remapped);
    c.slot_images[5].flags=static_cast<unsigned>(ImageFlagBits::CpuModified);
    assert(c.Run(guest).empty());
    c.slot_images[2].flags=0;
    c.slot_images[3].flags=0;
    assert((c.Run(guest)==std::vector<int>{3}));
    c.slot_images[6].flags=0; // Fresh decode published.
    assert((c.Run(guest)==std::vector<int>{6}));
    // First equal-tick candidate wins, just like the original max_element.
    c.slot_images[2].modification_tick=100;
    c.slot_images[3].modification_tick=100;
    c.image_map_ids={2,3};
    assert((c.Run(guest)==std::vector<int>{2}));
    c.image_map_ids={3,2};
    assert((c.Run(guest)==std::vector<int>{3}));
    // More than the old inline capacity: bounded O(1) selection state.
    c.image_map_ids={1,2,3,4,5,6,7};
    for(int i=1;i<=7;++i) {
        c.slot_images[i].flags=0;
        c.slot_images[i].image_view_ids={i};
        c.slot_images[i].modification_tick=i;
    }
    assert((c.Run(guest)==std::vector<int>{7}));
    for(int i=1;i<=7;++i) c.slot_images[i].cpu_addr=guest+1;
    assert(c.Run(guest).empty());
}
'''.replace("__SOURCE_DECLARE__", declaration).replace("__SOURCE_LOOP__", loop).replace("__SOURCE_SELECT__", selection)

with tempfile.TemporaryDirectory(prefix="encore-f07-present-fresh-") as d:
    src=Path(d)/"fresh.cpp"
    src.write_text(cpp)
    for optimization in ("-O0","-O2"):
        out=Path(d)/optimization
        subprocess.run(["c++","-std=c++20",optimization,"-DPS5_NATIVE",
                        "-Wall","-Wextra","-Werror",str(src),"-o",str(out)],check=True,timeout=60)
        subprocess.run([str(out)],check=True,timeout=15)
        print("F07_PRESENT_FRAMEBUFFER_FRESHNESS_PASS",optimization)
