#!/usr/bin/env python3
"""F07 P0.3: execute real native inline DMA code with conservative buffer-page evidence.

Asserts the guest copy and shader/query invalidation cannot be removed when
the buffer cache mutex is elided. Previously owned, uncertain, cross-page
and large ranges preserve both cache paths. Does not test GPU driver timing.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
active = (ROOT/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
bridge = (ROOT/"vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp").read_text()
pinned = (ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
generator = (ROOT/"tools/prepare-vulkan-port.py").read_text()
owner = (ROOT/"vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
tracker = (ROOT/"vendor/sources/eden/src/video_core/buffer_cache/word_manager.h").read_text()
fast = (ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
pre = (ROOT/".github/workflows/encore-core-preflight.yml").read_text()
invocation = "python3 -B tools/check-ps5-f07-inline-dma-buffer-elision-host.py"
assert invocation in fast and invocation in pre
assert "F07 elide never-owned inline DMA buffer cache mutex" in generator
start = "void RasterizerVulkan::AccelerateInlineToMemory("
end = "\nstd::optional<FramebufferTextureInfo> RasterizerVulkan::AccelerateDisplay("
def method(text):
    assert text.count(start) == text.count(end) == 1
    return text[text.index(start):text.index(end,text.index(start))]
selected = method(active)
assert selected == method(bridge), "native and DEV bridge must match"
assert selected != method(pinned)
assert selected.count("::Eden::BufferPages::NeverRegistered(*cpu_addr, copy_size)") == 1
assert selected.count("::Eden::ImagePages::NeverHeld(*cpu_addr, copy_size)") == 1
assert selected.index("gpu_memory->WriteBlockUnsafe(") < selected.index("BufferPages::NeverRegistered(")
assert selected.index("BufferPages::NeverRegistered(") < selected.index("buffer_cache.InlineMemory(")
assert selected.index("buffer_cache.InlineMemory(") < selected.index("ImagePages::NeverHeld(")
assert selected.index("ImagePages::NeverHeld(") < selected.index("pipeline_cache.InvalidateRegion(")
assert selected.index("pipeline_cache.InvalidateRegion(") < selected.index("query_cache.InvalidateRegion(")
assert selected.count("gpu_memory->WriteBlock(address, memory.data(), copy_size);") == 1
assert "std::fill_n(heap.data() + size_t(Type::CPU) * num_words, num_words, ~u64{0});" in tracker
registration = owner[owner.index("void BufferCache<P>::ChangeRegister("):]
assert registration.index("::Eden::BufferPages::Mark(buffer.CpuAddr(), size);") < registration.index("page_table[page] = buffer_id;")
assert "bool BufferCache<P>::InlineMemory(" in owner
assert "const bool is_dirty = IsRegionRegistered(dest_address, copy_size);" in owner

cpp = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <optional>
#include <span>
#include <vector>
#include "buffer_pages.h"
#include "image_pages.h"
using u8=std::uint8_t;
using u64=std::uint64_t;
using DAddr=u64;
using GPUVAddr=u64;
struct MockMemory {
    std::vector<u8> bytes=std::vector<u8>(2*1024*1024,0);
    bool mapped=true;
    unsigned unsafe_writes=0, fallback_writes=0;
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr a) {
        return mapped ? std::optional<DAddr>{a} : std::nullopt;
    }
    void WriteBlock(GPUVAddr a,const void* src,std::size_t size) {
        assert(a<=bytes.size() && size<=bytes.size()-a);
        std::memcpy(bytes.data()+a,src,size);
        ++fallback_writes;
    }
    void WriteBlockUnsafe(GPUVAddr a,const void* src,std::size_t size) {
        assert(a<=bytes.size() && size<=bytes.size()-a);
        std::memcpy(bytes.data()+a,src,size);
        ++unsafe_writes;
    }
};
struct BufferCache {
    std::recursive_mutex mutex;
    MockMemory* memory{};
    unsigned inline_calls=0, writes=0;
    bool inline_accepted=false;
    bool InlineMemory(DAddr a,std::size_t size,std::span<const u8> bytes) {
        ++inline_calls;
        assert(memory && memory->unsafe_writes==1);
        assert(std::equal(bytes.begin(),bytes.begin()+size,memory->bytes.begin()+a));
        return inline_accepted;
    }
    void WriteMemory(DAddr,std::size_t) {++writes;}
};
struct TextureCache {
    std::recursive_mutex mutex;
    unsigned writes=0;
    void WriteMemory(DAddr,std::size_t) {++writes;}
};
struct Cache {
    unsigned writes=0;
    void InvalidateRegion(DAddr,std::size_t) {++writes;}
};
struct RasterizerVulkan {
    MockMemory storage;
    MockMemory* gpu_memory=&storage;
    BufferCache buffer_cache;
    TextureCache texture_cache;
    Cache pipeline_cache,query_cache;
    RasterizerVulkan() {buffer_cache.memory=&storage;}
    void AccelerateInlineToMemory(GPUVAddr,std::size_t,std::span<const u8>);
};
""" + selected + r"""
int main() {
    using namespace Eden;
    constexpr DAddr blank=0x10000;
    constexpr DAddr formerly=0x20000;
    constexpr DAddr image_only=0x30000;
    constexpr DAddr unknown=0x40000;
    constexpr DAddr cross_page=0x4fffe;
    constexpr DAddr large=0x80000;
    const std::array<u8,8> payload{12,34,56,78,90,11,22,33};
    RasterizerVulkan fresh;
    fresh.AccelerateInlineToMemory(blank,payload.size(),payload);
    assert(fresh.storage.unsafe_writes==1 && fresh.storage.fallback_writes==0);
    assert(std::equal(payload.begin(),payload.end(),fresh.storage.bytes.begin()+blank));
    assert(fresh.buffer_cache.inline_calls==0 && fresh.buffer_cache.writes==0);
    assert(fresh.texture_cache.writes==0);
    assert(fresh.pipeline_cache.writes==1 && fresh.query_cache.writes==1);
    // A registration after the earlier write must not inherit stale GPU state.
    BufferPages::Mark(blank,4096);
    RasterizerVulkan after_registration;
    after_registration.AccelerateInlineToMemory(blank,payload.size(),payload);
    assert(after_registration.buffer_cache.inline_calls==1);
    assert(after_registration.buffer_cache.writes==1);
    assert(after_registration.pipeline_cache.writes==1);

    BufferPages::Mark(formerly,4096);
    RasterizerVulkan occupied;
    occupied.buffer_cache.inline_accepted=true;
    occupied.AccelerateInlineToMemory(formerly,payload.size(),payload);
    assert(occupied.buffer_cache.inline_calls==1 && occupied.buffer_cache.writes==0);
    assert(occupied.pipeline_cache.writes==1 && occupied.query_cache.writes==1);
    // Old ownership is monotonic even after the GPU slot is evicted.
    occupied.AccelerateInlineToMemory(formerly,payload.size(),payload);
    assert(occupied.buffer_cache.inline_calls==2);

    ImagePages::Mark(image_only,4096);
    RasterizerVulkan tex;
    tex.AccelerateInlineToMemory(image_only,payload.size(),payload);
    assert(tex.buffer_cache.inline_calls==0 && tex.texture_cache.writes==1);
    assert(tex.pipeline_cache.writes==1 && tex.query_cache.writes==1);

    BufferPages::Mark(0x50000,4096);
    RasterizerVulkan boundary;
    boundary.AccelerateInlineToMemory(cross_page,payload.size(),payload);
    assert(boundary.buffer_cache.inline_calls==1 && boundary.buffer_cache.writes==1);

    RasterizerVulkan unmapped;
    unmapped.storage.mapped=false;
    unmapped.AccelerateInlineToMemory(unknown,payload.size(),payload);
    assert(unmapped.storage.unsafe_writes==0 && unmapped.storage.fallback_writes==1);
    assert(unmapped.buffer_cache.inline_calls==0 && unmapped.texture_cache.writes==0);
    assert(unmapped.pipeline_cache.writes==0 && unmapped.query_cache.writes==0);

    RasterizerVulkan huge;
    std::vector<u8> big(300*1024,u8{0x7a});
    huge.AccelerateInlineToMemory(large,big.size(),big);
    assert(huge.buffer_cache.inline_calls==1 && huge.buffer_cache.writes==1);
    assert(huge.texture_cache.writes==1);
    assert(huge.pipeline_cache.writes==1 && huge.query_cache.writes==1);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"host C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-inline-dma-elision-") as tmp:
    source_file=Path(tmp)/"inline.cpp"
    source_file.write_text(cpp)
    for opt in ("-O0","-O2"):
        exe=Path(tmp)/("inline"+opt[1:])
        built=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                              "-fsanitize=undefined","-fno-sanitize-recover=all",
                              "-I",str(ROOT/"headless"),str(source_file),"-o",str(exe)],
                             capture_output=True,text=True,timeout=60)
        assert built.returncode==0,(opt,built.stderr[-6000:])
        ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
        assert ran.returncode==0,(opt,ran.stdout,ran.stderr[-6000:])
print("F07_INLINE_DMA_BUFFER_MUTEX_ELISION_HOST_PASS pristine=1 future_register=1"
      " previously_owned=1 gpu_dirty_inline=1 image_only=1 cross_page=1"
      " no_mapping=1 large_fails_closed=1 O0=1 O2=1")
