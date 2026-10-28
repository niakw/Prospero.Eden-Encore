#!/usr/bin/env python3
"""Source parity and actual C++ DMA extent arithmetic under ASan/UBSan."""
from pathlib import Path
import shutil,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
def read(p):return (root/p).read_text()
pinned=read("vendor/sources/eden/src/video_core/engines/maxwell_dma.cpp")
native=read("vendor/encore-active/eden-core/src/video_core/engines/maxwell_dma.cpp")
vulkan=read("vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp")
bridge=read("vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp")
cm=read("headless/CMakeLists.txt")
wf=read(".github/workflows/encore-core-preflight.yml")
o="    dst_operand.pitch = static_cast<u32>(std::abs(regs.pitch_out));"
n="    // Widen before absolute value: s32 minimum cannot be negated in s32.\n    dst_operand.pitch = static_cast<u32>(std::abs(static_cast<s64>(regs.pitch_out)));"
assert pinned.count(o)==1
expected=pinned.replace(o,n)
pairs=[
("    const size_t dst_size = dst_operand.pitch * regs.line_count;",
"""    const u64 dst_size_wide = static_cast<u64>(dst_operand.pitch) * regs.line_count;
    if (dst_size_wide > static_cast<u64>(~u32{0})) {
        LOG_WARNING(Render_OpenGL, "Oversized DMA linear destination");
        return;
    }
    const size_t dst_size = static_cast<size_t>(dst_size_wide);"""),
("    const size_t src_size = static_cast<size_t>(regs.pitch_in) * regs.line_count;",
"""    const u64 src_size_wide = static_cast<u64>(regs.pitch_in) * regs.line_count;
    if (src_size_wide > static_cast<u64>(~u32{0})) {
        LOG_WARNING(Render_OpenGL, "Oversized DMA linear source");
        return;
    }
    const size_t src_size = static_cast<size_t>(src_size_wide);"""),
("""    const u32 pitch = x_elements * bytes_per_pixel;
    const size_t mid_buffer_size = pitch * regs.line_count;""",
"""    const u64 pitch_wide = static_cast<u64>(x_elements) * bytes_per_pixel;
    const u64 max_transfer = static_cast<u64>(~u32{0});
    if (pitch_wide > max_transfer ||
        (regs.line_count != 0 && pitch_wide > max_transfer / regs.line_count)) {
        LOG_WARNING(Render_OpenGL, "Oversized DMA intermediate buffer");
        return;
    }
    const u32 pitch = static_cast<u32>(pitch_wide);
    const size_t mid_buffer_size = static_cast<size_t>(pitch_wide * regs.line_count);""")]
for a,b in pairs:
 assert expected.count(a)==1
 expected=expected.replace(a,b)
# An exact maintained-source parity extension: source is pinned plus
# only the audited extent fixes and the non-overlap contiguous DMA fold.
assert expected.count("using namespace Texture;" + chr(10)*2)==1
expected=expected.replace("using namespace Texture;" + chr(10)*2, "using namespace Texture;" + chr(10)*2 + "namespace {\n// Fold a row-wise DMA into one guest-memory copy only when every row is\n// contiguous, both byte ranges are representable and do not overlap.\nconstexpr bool CanCoalescePitchDma(u64 source, u64 dest, u32 width, u32 rows,\n                                   s64 pitch_in, s64 pitch_out, u64& total) noexcept {\n    total = 0;\n    if (width == 0 || rows == 0 || pitch_in != static_cast<s64>(width) ||\n        pitch_out != static_cast<s64>(width) ||\n        width > (~u32{0}) / rows) {\n        return false;\n    }\n    const u64 bytes = static_cast<u64>(width) * rows;\n    if (source > ~u64{0} - bytes || dest > ~u64{0} - bytes) {\n        return false;\n    }\n    if (!(source + bytes <= dest || dest + bytes <= source)) {\n        return false;\n    }\n    total = bytes;\n    return true;\n}\n} // namespace\n\n")
original_pitch_loop="        if (is_src_pitch && is_dst_pitch) {\n            for (u32 line = 0; line < regs.line_count; ++line) {\n                const GPUVAddr source_line =\n                    regs.offset_in + static_cast<size_t>(line) * regs.pitch_in;\n                const GPUVAddr dest_line =\n                    regs.offset_out + static_cast<size_t>(line) * regs.pitch_out;\n                memory_manager.CopyBlock(dest_line, source_line, regs.line_length_in);\n            }\n        } else {"
folded_pitch_loop="        if (is_src_pitch && is_dst_pitch) {\n            u64 contiguous_bytes = 0;\n            if (CanCoalescePitchDma(regs.offset_in, regs.offset_out, regs.line_length_in,\n                                    regs.line_count, regs.pitch_in, regs.pitch_out,\n                                    contiguous_bytes)) {\n                // A single mapped copy/flush avoids a row-wise GPU memory walk.\n                memory_manager.CopyBlock(regs.offset_out, regs.offset_in,\n                                         static_cast<size_t>(contiguous_bytes));\n            } else {\n                // Retain exact row-by-row semantics for overlapping, gapped,\n                // negative-pitch or large transfers.\n                for (u32 line = 0; line < regs.line_count; ++line) {\n                    const GPUVAddr source_line =\n                        regs.offset_in + static_cast<size_t>(line) * regs.pitch_in;\n                    const GPUVAddr dest_line =\n                        regs.offset_out + static_cast<size_t>(line) * regs.pitch_out;\n                    memory_manager.CopyBlock(dest_line, source_line, regs.line_length_in);\n                }\n            }\n        } else {"
assert expected.count(original_pitch_loop)==1
expected=expected.replace(original_pitch_loop,folded_pitch_loop)
assert expected==native
assert "EDEN_MAINTAINED_MAXWELL_DMA" in cm
assert 'list(REMOVE_ITEM video_sources engines/maxwell_dma.cpp)' in cm
assert 'python3 -B tools/check-native-dma-extent-host.py' in wf
gpu="""    // Widen before multiplying, then respect the u32 buffer-cache span.
    const u64 buffer_size_wide = static_cast<u64>(buffer_operand.pitch) * buffer_operand.height;
    if (buffer_size_wide > static_cast<u64>(~u32{0})) {
        return false;
    }
    const u32 buffer_size = static_cast<u32>(buffer_size_wide);"""
assert gpu in vulkan and gpu in bridge
def cut(s,start,end):
 assert s.count(start)==1
 pos=s.index(start)
 return s[pos:s.index(end,pos)].strip()+"\n"
dst=cut(native,"    const u64 dst_size_wide","\n    Tegra::Memory::GpuGuestMemory<u8")
src=cut(native,"    const u64 src_size_wide","\n    GPUVAddr src_addr")
mid=cut(native,"    const u64 pitch_wide","\n    intermediate_buffer.resize_destructive")
acc=cut(vulkan,"    const u64 buffer_size_wide","\n#endif\n    static constexpr auto sync_info")
# The extracted desktop arithmetic is inside #else; keep its closing #endif out.
assert "#else\n    // Widen before multiplying" in vulkan
cpp=r"""
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstddef>
#include <optional>
using u32=std::uint32_t; using u64=std::uint64_t;
using s32=std::int32_t; using s64=std::int64_t;
#define LOG_WARNING(...) ((void)0)
struct Regs{u32 pitch_in;u32 line_count;};
struct Buf{u32 pitch;u32 height;};
std::optional<std::size_t> Dst(u32 pitch,u32 count){
 Buf dst_operand{pitch,0};Regs regs{0,count};
__DST__
 return dst_size;
}
std::optional<std::size_t> Src(u32 pitch,u32 count){
 Regs regs{pitch,count};
__SRC__
 return src_size;
}
std::optional<std::size_t> Mid(u32 x_elements,u32 bytes_per_pixel,u32 count){
 Regs regs{0,count};
__MID__
 (void)pitch;return mid_buffer_size;
}
bool Acc(u32 pitch,u32 height){
 Buf buffer_operand{pitch,height};
__ACC__
 return buffer_size==static_cast<u32>(static_cast<u64>(pitch)*height);
}
int main(){
 const u32 mx=~u32{0};
 assert(Acc(0,0) && Acc(256,1080) && Acc(mx,1));
 assert(!Acc(65536,65536) && !Acc(mx,2));
 assert(Dst(256,1080)==std::optional<std::size_t>{276480});
 assert(Src(256,1080)==std::optional<std::size_t>{276480});
 assert(!Dst(65536,65536) && !Src(65536,65536));
 assert(Dst(mx,1)==std::optional<std::size_t>{mx});
 assert(Mid(256,4,1080)==std::optional<std::size_t>{1105920});
 assert(Mid(mx,1,1)==std::optional<std::size_t>{mx});
 assert(!Mid(mx,2,1) && !Mid(mx,1,2));
 assert(!Mid(mx,mx,mx));
 assert(static_cast<u32>(std::abs(static_cast<s64>(-2147483647-1)))==2147483648u);
}
"""
for key,body in (("__DST__",dst),("__SRC__",src),("__MID__",mid),("__ACC__",acc)):
 assert cpp.count(key)==1
 cpp=cpp.replace(key,body.replace("return;","return std::nullopt;"))
clang=shutil.which("clang++-18") or shutil.which("clang++")
assert clang
with tempfile.TemporaryDirectory(prefix="dma-extent-") as td:
 f=Path(td)/"main.cpp";out=Path(td)/"test";f.write_text(cpp)
 subprocess.run([clang,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
                 "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                 str(f),"-o",str(out)],check=True,timeout=55)
 subprocess.run([str(out)],check=True,timeout=20)
print("DMA_EXTENT_HOST_PASS real_arithmetic=4 native_owner=1 pinned_parity=1 asan_ubsan=1")
