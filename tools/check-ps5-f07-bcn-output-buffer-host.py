#!/usr/bin/env python3
"""Source-extracted BCn 3D Vulkan output-buffer growth, overflow, retry."""
from pathlib import Path
import shutil, subprocess, tempfile

root=Path(__file__).resolve().parents[1]
active=(root/"vendor/encore-active/eden-vulkan/vk_texture_cache_cost.cpp").read_text()
pinned=(root/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_texture_cache.cpp").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
a="void Image::AllocateComputeUnswizzleBuffer("
b="\nvoid Image::UploadMemory("
def extract(s):
    start=s.index(a)
    return s[start:s.index(b,start)]
method=extract(active)
baseline=extract(pinned)
assert method != baseline
assert "#ifdef PS5_NATIVE" in method
assert "F07 PS5 transactional BCn 3D compute output buffer" in gen
assert method.count("compute_unswizzle_buffer_size = required_size;") == 2
assert method.index("runtime->memory_allocator.CreateBuffer(ci, MemoryUsage::DeviceLocal)") < method.rindex("compute_unswizzle_buffer_size = required_size;")
assert "blocks_xy > max_buffer / blocks_z" in method
for path in (".github/workflows/encore-core-fast-gate.yml",
             ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-bcn-output-buffer-host.py" in (root/path).read_text()
cpp=r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <limits>
#include <memory>
#include <new>
#include <utility>
using u32=std::uint32_t;
using u64=std::uint64_t;
using VkDeviceSize=u64;
constexpr int VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO=12;
constexpr int VK_BUFFER_USAGE_STORAGE_BUFFER_BIT=1;
constexpr int VK_BUFFER_USAGE_TRANSFER_SRC_BIT=2;
constexpr int VK_SHARING_MODE_EXCLUSIVE=0;
enum class MemoryUsage { DeviceLocal };
struct VkBufferCreateInfo {
    int sType;
    const void* pNext;
    int flags;
    VkDeviceSize size;
    int usage;
    int sharingMode;
    int queueFamilyIndexCount;
    const u32* pQueueFamilyIndices;
};
struct Buffer { VkDeviceSize size; };
struct Allocator {
    unsigned requests{};
    bool fail{};
    std::unique_ptr<Buffer> CreateBuffer(const VkBufferCreateInfo& ci,MemoryUsage) {
        ++requests;
        if (fail) throw std::bad_alloc{};
        return std::make_unique<Buffer>(Buffer{ci.size});
    }
};
struct Runtime { Allocator memory_allocator; };
struct Info {
    struct {u32 width;u32 height;u32 depth;} size;
    u32 format;
};
namespace VideoCore::Surface {
    u32 BytesPerBlock(u32 format) { return format; }
}
struct Image {
    Info info;
    Runtime* runtime;
    VkDeviceSize compute_unswizzle_buffer_size{};
    bool has_compute_unswizzle_buffer{};
    std::unique_ptr<Buffer> compute_unswizzle_buffer{};
    void AllocateComputeUnswizzleBuffer(u32 max_slices);
};
""" + method + r"""
int main() {
    Runtime runtime{};
    Image image{{{16,16,8},16}, &runtime};
    image.AllocateComputeUnswizzleBuffer(2);
    assert(runtime.memory_allocator.requests==1);
    assert(image.has_compute_unswizzle_buffer);
    assert(image.compute_unswizzle_buffer_size==512);
    assert(image.compute_unswizzle_buffer->size==512);
    image.AllocateComputeUnswizzleBuffer(1);
    assert(runtime.memory_allocator.requests==1);
    runtime.memory_allocator.fail=true;
    bool failed=false;
    try { image.AllocateComputeUnswizzleBuffer(4); }
    catch(const std::bad_alloc&) { failed=true; }
    assert(failed && runtime.memory_allocator.requests==2);
    assert(image.compute_unswizzle_buffer->size==512);
#ifdef PS5_NATIVE
    assert(image.compute_unswizzle_buffer_size==512);
#else
    assert(image.compute_unswizzle_buffer_size==1024);
#endif
    runtime.memory_allocator.fail=false;
    image.AllocateComputeUnswizzleBuffer(4);
#ifdef PS5_NATIVE
    assert(runtime.memory_allocator.requests==3);
    assert(image.compute_unswizzle_buffer->size==1024);
#else
    // Desktop's historical eager size advertisement skips the retry.
    assert(runtime.memory_allocator.requests==2);
    assert(image.compute_unswizzle_buffer->size==512);
#endif
#ifdef PS5_NATIVE
    const auto rejected=[&](u32 width,u32 height,u32 depth,u32 bytes,u32 slices) {
        Runtime local{};
        Image candidate{{{width,height,depth},bytes}, &local};
        bool got_error=false;
        try { candidate.AllocateComputeUnswizzleBuffer(slices); }
        catch (const std::bad_alloc&) { got_error=true; }
        assert(got_error && local.memory_allocator.requests==0);
        assert(!candidate.has_compute_unswizzle_buffer);
    };
    rejected(0,16,2,16,1);
    rejected(16,0,2,16,1);
    rejected(16,16,2,16,0);
    rejected(16,16,0,16,1);
    rejected(16,16,2,0,1);
    rejected(~u32{0},16,2,16,1);
    rejected(16,~u32{0},2,16,1);
    rejected(~u32{0}-3,~u32{0}-3,~u32{0},16,~u32{0});
    Runtime huge{};
    Image still_valid{{{65536,65536,16},16}, &huge};
    still_valid.AllocateComputeUnswizzleBuffer(16);
    assert(huge.memory_allocator.requests==1);
    assert(still_valid.compute_unswizzle_buffer_size==(u64{1}<<32));
#endif
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-bcn-output-") as directory:
    src=Path(directory)/"output.cpp"
    src.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            out=Path(directory)/(("ps5" if native else "desktop")+opt[1:])
            defines=["-DPS5_NATIVE=1"] if native else []
            result=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                "-fsanitize=undefined","-fno-sanitize-recover=all",*defines,str(src),"-o",str(out)],
                capture_output=True,text=True,timeout=40)
            assert result.returncode==0,(native,opt,result.stderr[-5000:])
            ran=subprocess.run([str(out)],capture_output=True,text=True,timeout=15)
            assert ran.returncode==0,(native,opt,ran.stderr[-4000:])
print("F07_BCN_OUTPUT_BUFFER_PASS transactional_retry=1 no_empty=1 zero_slices=1 no_u64_wrap=1 native=1 desktop_original=1 O0=1 O2=1 UBSan=1")
