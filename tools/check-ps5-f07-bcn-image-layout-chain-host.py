#!/usr/bin/env python3
"""F07 BCn 3D partial batch image layout must match previous post barrier."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-vulkan/vk_compute_pass_cost.cpp").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
begin=src.index("void BlockLinearUnswizzle3DPass::UnswizzleChunk(")
method=src[begin:src.index("\n} // namespace Vulkan",begin)]
def initializer(token):
    pos=method.index(token)
    end=method.index("        };",pos)+len("        };")
    return method[pos:end]
pre=initializer("const VkImageMemoryBarrier pre_barrier{")
post=initializer("const VkImageMemoryBarrier post_barrier{")
assert "F07 preserve native BCn 3D image layout between GPU batches" in gen
assert "F07 synchronize native BCn 3D reused image before transfer" in gen
assert "F07 avoid all commands source barrier for first native BCn3D batch" in gen
assert "VK_IMAGE_LAYOUT_GENERAL" in pre
assert "VK_IMAGE_LAYOUT_GENERAL" in post
assert method.index("VK_PIPELINE_STAGE_ALL_COMMANDS_BIT") < method.index(
    "VK_PIPELINE_STAGE_TRANSFER_BIT,\\n            0,\\n            nullptr, buffer_barrier, pre_barrier")
# Extract the source-selected stage expression, not an independently
# invented equivalent, to exercise first vs reused chunks in a C++ fixture.
barrier_start=method.index("cmdbuf.PipelineBarrier(", method.index("Single barrier handles both buffer and image."))
stage_src=method[barrier_start:]
stage_fragment=stage_src[stage_src.index("#ifdef PS5_NATIVE"):stage_src.index("            VK_PIPELINE_STAGE_TRANSFER_BIT,")]
assert stage_fragment.count("VK_PIPELINE_STAGE_ALL_COMMANDS_BIT")==1
assert stage_fragment.count("VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT")==2
assert "is_first_chunk ? VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT :" in stage_fragment
stage_fragment=stage_fragment.rstrip().removesuffix(",")+";"

for wf in (".github/workflows/encore-core-fast-gate.yml",
           ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-bcn-image-layout-chain-host.py" in (root/wf).read_text()
cpp=r"""
#include <cassert>
#include <cstdint>
using VkAccessFlags=std::uint32_t;
using VkPipelineStageFlags=std::uint32_t;
constexpr VkPipelineStageFlags VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT=0x10;
constexpr VkPipelineStageFlags VK_PIPELINE_STAGE_ALL_COMMANDS_BIT=0x100;
using VkImage=std::uint64_t;
using VkImageAspectFlags=std::uint32_t;
struct SubresourceRange { VkImageAspectFlags aspect; int mip; int levels; int layer; int layers; };
struct VkImageMemoryBarrier {
    int sType; const void* pNext; VkAccessFlags srcAccessMask;
    VkAccessFlags dstAccessMask; int oldLayout; int newLayout;
    std::uint32_t srcQueueFamilyIndex, dstQueueFamilyIndex;
    VkImage image; SubresourceRange subresourceRange;
};
constexpr int VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER=1;
constexpr unsigned VK_ACCESS_TRANSFER_WRITE_BIT=0x1;
constexpr unsigned VK_ACCESS_SHADER_READ_BIT=0x2;
constexpr unsigned VK_ACCESS_SHADER_WRITE_BIT=0x4;
constexpr unsigned VK_ACCESS_MEMORY_READ_BIT=0x8;
constexpr unsigned VK_ACCESS_MEMORY_WRITE_BIT=0x10;
constexpr int VK_IMAGE_LAYOUT_UNDEFINED=0;
constexpr int VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL=1;
constexpr int VK_IMAGE_LAYOUT_GENERAL=2;
constexpr std::uint32_t VK_QUEUE_FAMILY_IGNORED=~std::uint32_t{};
VkPipelineStageFlags SrcStage(bool is_first_chunk) {
    const VkPipelineStageFlags stage =
""" + stage_fragment + r"""
    return stage;
}
VkImageMemoryBarrier Pre(bool is_first_chunk) {
    const VkImage dst_image=55;
    const VkImageAspectFlags aspect=7;
""" + pre + r"""
    return pre_barrier;
}
VkImageMemoryBarrier Post() {
    const VkImage dst_image=55;
    const VkImageAspectFlags aspect=7;
""" + post + r"""
    return post_barrier;
}
int main() {
    auto first=Pre(true);
    auto next=Pre(false);
    const auto post=Post();
#ifdef PS5_NATIVE
    assert(SrcStage(true)==VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT);
    assert(SrcStage(false)==VK_PIPELINE_STAGE_ALL_COMMANDS_BIT);
#else
    assert(SrcStage(true)==VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT);
    assert(SrcStage(false)==VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT);
#endif
    assert(first.oldLayout==VK_IMAGE_LAYOUT_UNDEFINED);
    assert(first.srcAccessMask==0);
    assert(first.newLayout==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
    assert(post.oldLayout==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
    assert(post.newLayout==VK_IMAGE_LAYOUT_GENERAL);
    assert(post.srcAccessMask==VK_ACCESS_TRANSFER_WRITE_BIT);
#ifdef PS5_NATIVE
    assert(next.oldLayout==post.newLayout);
    assert((next.srcAccessMask & VK_ACCESS_MEMORY_WRITE_BIT)!=0);
    assert((next.srcAccessMask & VK_ACCESS_MEMORY_READ_BIT)!=0);
#else
    assert(next.oldLayout==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
    assert(next.srcAccessMask==VK_ACCESS_TRANSFER_WRITE_BIT);
#endif
    assert(next.newLayout==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
    assert(next.image==post.image);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-bcn-layout-") as td:
    path=Path(td)/"layout.cpp"
    path.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            out=Path(td)/(("ps5" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(['-DPS5_NATIVE=1'] if native else []),str(path),"-o",str(out)]
            b=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
            assert b.returncode==0,(native,opt,b.stderr[-4000:])
            t=subprocess.run([str(out)],capture_output=True,text=True,timeout=10)
            assert t.returncode==0,(native,opt,t.stderr[-3000:])
print("F07_BCN3D_LAYOUT_CHAIN_PASS first_undefined=1 next_general=1 post_general=1 first_compute_only=1 reused_all_commands_native=1 original_desktop=1 O0=1 O2=1 UBSan=1")
