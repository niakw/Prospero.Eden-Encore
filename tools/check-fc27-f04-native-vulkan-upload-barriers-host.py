#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F04: source-extracted Vulkan upload copy/barrier stage and access proof.

Compile the selected CopyBufferToImage helper and its mip/layer range under
O0 and O2 with mock command recording and UBSan. Check transfer-write ->
fragment/vertex shader reads, previous transfer writes, and attachment
writers without issuing a real Vulkan command buffer or sampling GPU pixels.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/"vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp").read_text()
fast=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
cmake=(ROOT/"headless/vulkan.cmake").read_text()
command="python3 -B tools/check-fc27-f04-native-vulkan-upload-barriers-host.py"
assert command in fast and command in pre
# The maintained file is selected by CMake's cost suffix loop, not a
# literal complete filename in the recipe.
assert "foreach(name vk_fence_manager vk_buffer_cache vk_texture_cache" in cmake
assert 'list(APPEND video_sources "${PORT_BUILD_DIR}/${name}_cost.cpp")' in cmake
start="struct RangedBarrierRange {"
end="\n[[nodiscard]] VkImageBlit MakeImageBlit("
assert source.count(start)==1 and source.count(end)==1
segment=source[source.index(start):source.index(end,source.index(start))]
assert segment.count("void CopyBufferToImage(")==1
assert "VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT" in segment
assert "VK_ACCESS_TRANSFER_WRITE_BIT" in segment
assert "VK_PIPELINE_STAGE_TRANSFER_BIT" in segment
assert segment.count("cmdbuf.PipelineBarrier(")==2
assert segment.count("cmdbuf.CopyBufferToImage(")==1

cpp=r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <span>
#include <vector>
using u32=std::uint32_t;
using VkBuffer=std::uint64_t;
using VkImage=std::uint64_t;
using VkPipelineStageFlags=u32;
using VkAccessFlags=u32;
using VkImageAspectFlags=u32;
using VkImageLayout=u32;
constexpr u32 VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER=1;
constexpr u32 VK_QUEUE_FAMILY_IGNORED=~u32{0};
constexpr u32 VK_IMAGE_LAYOUT_UNDEFINED=0;
constexpr u32 VK_IMAGE_LAYOUT_GENERAL=1;
constexpr u32 VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL=2;
constexpr u32 VK_ACCESS_SHADER_WRITE_BIT=1<<0;
constexpr u32 VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT=1<<1;
constexpr u32 VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT=1<<2;
constexpr u32 VK_ACCESS_SHADER_READ_BIT=1<<3;
constexpr u32 VK_ACCESS_COLOR_ATTACHMENT_READ_BIT=1<<4;
constexpr u32 VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT=1<<5;
constexpr u32 VK_ACCESS_TRANSFER_WRITE_BIT=1<<6;
constexpr u32 VK_ACCESS_TRANSFER_READ_BIT=1<<7;
constexpr u32 VK_PIPELINE_STAGE_VERTEX_SHADER_BIT=1<<0;
constexpr u32 VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT=1<<1;
constexpr u32 VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT=1<<2;
constexpr u32 VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT=1<<3;
constexpr u32 VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT=1<<4;
constexpr u32 VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT=1<<5;
constexpr u32 VK_PIPELINE_STAGE_TRANSFER_BIT=1<<6;
struct VkImageSubresourceLayers {
    u32 aspectMask{},mipLevel{},baseArrayLayer{},layerCount{};
};
struct VkImageSubresourceRange {
    u32 aspectMask{},baseMipLevel{},levelCount{},baseArrayLayer{},layerCount{};
};
struct VkBufferImageCopy {VkImageSubresourceLayers imageSubresource{};};
struct VkImageMemoryBarrier {
    u32 sType{};
    const void* pNext{};
    u32 srcAccessMask{},dstAccessMask{};
    VkImageLayout oldLayout{},newLayout{};
    u32 srcQueueFamilyIndex{},dstQueueFamilyIndex{};
    VkImage image{};
    VkImageSubresourceRange subresourceRange{};
};
struct Trace {
    u32 pre_src{},pre_dst{},post_src{},post_dst{};
    VkImageMemoryBarrier pre{},post{};
    std::vector<int> order;
    unsigned copies{}, regions{};
    VkBuffer buffer{};VkImage image{};
};
namespace vk {
struct CommandBuffer {
    Trace* trace{};
    void PipelineBarrier(u32 src,u32 dst,u32,
                         const VkImageMemoryBarrier& barrier) {
        assert(trace && trace->order.empty());
        trace->pre_src=src;trace->pre_dst=dst;
        trace->pre=barrier;trace->order.push_back(1);
    }
    void CopyBufferToImage(VkBuffer buffer,VkImage image,u32 layout,
                           std::span<const VkBufferImageCopy> copies) {
        assert(trace && trace->order.size()==1);
        assert(layout==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
        trace->copies++;trace->regions+=static_cast<unsigned>(copies.size());
        trace->buffer=buffer;trace->image=image;trace->order.push_back(2);
    }
    void PipelineBarrier(u32 src,u32 dst,u32,std::nullptr_t,std::nullptr_t,
                         const VkImageMemoryBarrier& barrier) {
        assert(trace && trace->order.size()==2);
        trace->post_src=src;trace->post_dst=dst;
        trace->post=barrier;trace->order.push_back(3);
    }
};
}
__SOURCE__
static void Check(bool initialized){
    Trace result{};
    constexpr VkImage image=19;
    constexpr VkBuffer buffer=88;
    constexpr VkImageAspectFlags aspect=3;
    const std::array<VkBufferImageCopy,2> copies{{
        {{aspect,2,4,2}},
        {{aspect,3,6,1}}
    }};
    CopyBufferToImage(vk::CommandBuffer{&result},buffer,image,aspect,initialized,copies);
    assert((result.order==std::vector<int>{1,2,3}));
    assert(result.copies==1 && result.regions==2);
    assert(result.image==image && result.buffer==buffer);
    assert(result.pre.oldLayout==(initialized?VK_IMAGE_LAYOUT_GENERAL:VK_IMAGE_LAYOUT_UNDEFINED));
    assert(result.pre.newLayout==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
    assert(result.post.oldLayout==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
    assert(result.post.newLayout==VK_IMAGE_LAYOUT_GENERAL);
    assert(result.pre.subresourceRange.baseMipLevel==2);
    assert(result.pre.subresourceRange.levelCount==2);
    assert(result.pre.subresourceRange.baseArrayLayer==4);
    assert(result.pre.subresourceRange.layerCount==3);
    assert(result.post.subresourceRange.baseMipLevel==2);
    // Previous transfer writes must be visible before overwriting.
    assert((result.pre.srcAccessMask&VK_ACCESS_TRANSFER_WRITE_BIT)!=0);
    assert((result.pre.srcAccessMask&VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT)!=0);
    assert((result.pre.srcAccessMask&VK_ACCESS_SHADER_WRITE_BIT)!=0);
    assert((result.pre.srcAccessMask&VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT)!=0);
    assert((result.pre_src&VK_PIPELINE_STAGE_TRANSFER_BIT)!=0);
    assert((result.pre_src&VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT)!=0);
    assert((result.pre_src&VK_PIPELINE_STAGE_VERTEX_SHADER_BIT)!=0);
    assert((result.pre_src&VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT)!=0);
    assert(result.pre_dst==VK_PIPELINE_STAGE_TRANSFER_BIT);
    assert(result.pre.dstAccessMask==VK_ACCESS_TRANSFER_WRITE_BIT);
    // A transfer write must be visible before vertex/fragment sampling.
    assert(result.post_src==VK_PIPELINE_STAGE_TRANSFER_BIT);
    assert((result.post.srcAccessMask&VK_ACCESS_TRANSFER_WRITE_BIT)!=0);
    assert((result.post.dstAccessMask&VK_ACCESS_SHADER_READ_BIT)!=0);
    assert((result.post.dstAccessMask&VK_ACCESS_TRANSFER_READ_BIT)!=0);
    assert((result.post_dst&VK_PIPELINE_STAGE_VERTEX_SHADER_BIT)!=0);
    assert((result.post_dst&VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT)!=0);
    assert((result.post_dst&VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT)!=0);
    assert((result.post_dst&VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT)!=0);
    assert((result.post_dst&VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT)!=0);
    assert((result.post_dst&VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT)!=0);
    assert((result.post_dst&VK_PIPELINE_STAGE_TRANSFER_BIT)!=0);
}
int main() {
    Check(false);
    Check(true);
    std::puts("F04_NATIVE_VULKAN_UPLOAD_BARRIER_PASS initial=1 reused=1 "
              "mip_layer_range=1 transfer_prior_writes=1 "
              "fragment_vertex_sampling=1 "
              "scope=source_extracted_host_mock_command_buffer");
}
""".replace("__SOURCE__",segment)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f04-vk-barriers-") as folder:
    file=Path(folder)/"barrier.cpp"
    file.write_text(cpp)
    for opt in ("-O0","-O2"):
        exe=Path(folder)/("barrier"+opt)
        built=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra",
            "-Werror","-fsanitize=undefined","-fno-sanitize-recover=all",
            str(file),"-o",str(exe)],capture_output=True,text=True,timeout=70)
        assert built.returncode==0,(opt,built.stderr[-5800:])
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
        assert run.returncode==0,(opt,run.stdout,run.stderr[-2800:])
        assert "F04_NATIVE_VULKAN_UPLOAD_BARRIER_PASS" in run.stdout
        print(run.stdout.strip(),opt,flush=True)
print("F04_REAL_GPU_SAMPLING_AND_VULKAN_DRIVER_UNVERIFIED")
