#!/usr/bin/env python3
"""F07 P0.4: native Vulkan image reinterpret coordinate conversion witness.

Compile the actual source-extracted format/offset preflight and source-side
VkBufferImageCopy transform. Native preserves widened arithmetic and rejects
invalid ratios/coordinates, while desktop retains its original conversion.
This cannot establish physical PS5 pixel correctness or FC27 frame rates.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/"vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp").read_text()
generator=(ROOT/"tools/prepare-vulkan-port.py").read_text()
fast=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
invocation="python3 -B tools/check-ps5-f07-reinterpret-coordinate-host.py"
assert invocation in fast and invocation in pre
assert "F07 validate native reinterpret pixel ratios before coordinate conversion" in generator
start=src.index("void TextureCacheRuntime::ReinterpretImage(")
end=src.index("\nvoid TextureCacheRuntime::BlitImage(",start)
body=src[start:end]
begin="#ifdef PS5_NATIVE\n    // Do not divide by an invalid format width"
finish="    std::ranges::transform(copies, vk_out_copies.begin(),"
assert body.count(begin)==body.count(finish)==1
# The optimized native path validates the full byte budget before
# allocating VkBufferImageCopy arrays. Extract only the format preflight
# and the later real input conversion into this focused C++ fixture.
size_start="    const u32 img_bpp = BytesPerBlock(dst.info.format);"
transform_start="    std::ranges::transform(copies, vk_in_copies.begin(),"
assert body.count(size_start)==body.count(transform_start)==1
assert body.index(size_start) < body.index(transform_start) < body.index(finish)
assert body.index("if (total_size > scratch_max)") < body.index(transform_start)
conversion=(body[body.index(begin):body.index(size_start)] +
            body[body.index(transform_start):body.index(finish)])
for token in ("if (src_block_width == 0 || dst_block_width == 0)",
              "if (bpp_in == 0 || bpp_out == 0)",
              "static_cast<s64>(copy.src_offset.x) < 0",
              "(static_cast<u64>(bpp_out) * copy.extent.width) / bpp_in",
              "scaled_width == 0",
              "std::numeric_limits<decltype(copy.src_offset.x)>::max",
              "std::numeric_limits<decltype(copy.extent.width)>::max",
              "copy2.src_offset.x = static_cast<decltype(copy2.src_offset.x)>",
              "copy2.extent.width = static_cast<decltype(copy2.extent.width)>"):
    assert token in conversion,token
assert conversion.index("for (const auto& copy : copies)") < conversion.index("std::ranges::transform")
assert conversion.index("if (bpp_in == 0 || bpp_out == 0)") < conversion.index("std::ranges::transform")

cpp=r"""
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <ranges>
#include <utility>
#include <vector>
using u32=std::uint32_t;
using u64=std::uint64_t;
using s64=std::int64_t;
using VkImageAspectFlags=u32;
struct Offset {std::int32_t x{};};
struct Extent {std::uint32_t width{},height{1},depth{1};};
struct ImageCopy {Offset src_offset{};Extent extent{};};
struct ImageInfo {u32 format{};};
struct Image {ImageInfo info;};
u32 DefaultBlockWidth(u32 format){return format==99 ? 0 : 1;}
u32 BytesPerBlock(u32 format){return format==99 ? 0 : format;}
ImageCopy MakeBufferImageCopy(const ImageCopy& x,bool, VkImageAspectFlags){return x;}
struct Probe {
    unsigned transforms{};
    std::vector<ImageCopy> result;
    void Convert(u32 source_format,u32 dest_format,const std::vector<ImageCopy>& copies) {
        if(copies.empty()) return;
        Image src{{source_format}},dst{{dest_format}};
        const VkImageAspectFlags src_aspect_mask=1;
        std::vector<ImageCopy> vk_in_copies(copies.size());
__PRODUCTION_TRANSFORM__
        ++transforms;
        result=vk_in_copies;
    }
};
int main(){
    // 16*(2^28) wraps u32 to zero, but 64-bit multiplication / 8
    // fits the signed offset. The PS5 variant must preserve 2^29.
    const ImageCopy large{{std::int32_t{1}<<28},{std::uint32_t{1}<<28,1,1}};
    Probe widened;
    widened.Convert(8,16,{large});
    assert(widened.transforms==1);
#ifdef PS5_NATIVE
    assert(widened.result[0].src_offset.x==(std::int32_t{1}<<29));
    assert(widened.result[0].extent.width==(std::uint32_t{1}<<29));
#else
    assert(widened.result[0].src_offset.x==0);
    assert(widened.result[0].extent.width==0);
#endif
    Probe regular;
    regular.Convert(8,16,{{{3},{5,2,1}}});
    assert(regular.transforms==1);
    assert(regular.result[0].src_offset.x==6);
    assert(regular.result[0].extent.width==10);
#ifdef PS5_NATIVE
    Probe bad_format;
    bad_format.Convert(99,16,{{{2},{5,1,1}}});
    assert(bad_format.transforms==0);
    Probe bad_offset;
    bad_offset.Convert(8,16,{{{-1},{5,1,1}}});
    assert(bad_offset.transforms==0);
    Probe offset_overflow;
    offset_overflow.Convert(1,16,{large});
    assert(offset_overflow.transforms==0);
    Probe extent_overflow;
    extent_overflow.Convert(1,16,{{{0},{std::uint32_t{1}<<28,1,1}}});
    assert(extent_overflow.transforms==0);
    Probe rounded_to_zero;
    rounded_to_zero.Convert(16,1,{{{0},{1,1,1}}});
    assert(rounded_to_zero.transforms==0);
#endif
}
""".replace("__PRODUCTION_TRANSFORM__",conversion)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"F07 native reinterpret coordinate witness needs C++20"
with tempfile.TemporaryDirectory(prefix="eden-f07-reinterpret-coordinate-") as folder:
    source=Path(folder)/"reinterpret.cpp"
    source.write_text(cpp)
    for opt in ("-O0","-O2"):
        for native in (False,True):
            binary=Path(folder)/("reinterpret"+opt[1:]+("-native" if native else "-desktop"))
            built=subprocess.run(
                [compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(['-DPS5_NATIVE=1'] if native else []),str(source),"-o",str(binary)],
                capture_output=True,text=True,timeout=50)
            assert built.returncode==0,(native,opt,built.stderr[-6500:])
            ran=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20)
            assert ran.returncode==0,(native,opt,ran.stderr[-6500:])
print("F07_REINTERPRET_COORDINATES_PASS native_widened_conversion=1 bad_ratio=1 negative_offset=1 range_overflow=1 zero_width=1 desktop_unchanged=1 O0=1 O2=1")
