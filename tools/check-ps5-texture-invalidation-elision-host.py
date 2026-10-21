#!/usr/bin/env python3
"""Host ASan/UBSan: source-extracted native Vulkan invalidation mutex gating.

Compile actual maintained methods, including original buffer/query/shader
invalidation paths. An unowned texture range may skip ONLY texture work.
A mixed batch retains the texture mutex but skips each provably unowned texture lookup.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
raster = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
bridge = (root / "vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
oracle = (root / "tools/prepare-vulkan-port.py").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
image_cache = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
assert "python3 -B tools/check-ps5-texture-invalidation-elision-host.py" in workflow
assert image_cache.index("::Eden::ImagePages::Mark(image.cpu_addr") < image_cache.index(
    "slot_map_views.insert(image.gpu_addr")
assert image_cache.index("::Eden::ImagePages::Mark(cpu_addr, size)") < image_cache.index(
    "slot_map_views.insert(gpu_addr, cpu_addr")
start = "void RasterizerVulkan::InvalidateRegion(DAddr addr, u64 size, VideoCommon::CacheType which) {"
mid = "bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {"
end0 = "void RasterizerVulkan::OnCacheInvalidation(DAddr addr, u64 size) {"
end1 = "void RasterizerVulkan::InvalidateGPUCache() {"
def methods(source):
    assert source.count(start) == source.count(mid) == source.count(end0) == source.count(end1) == 1
    return (source.split(start, 1)[1].split(mid, 1)[0],
            source.split(end0, 1)[1].split(end1, 1)[0])
new = methods(raster)
assert methods(bridge) == new, "inactive bridge invalidation methods drifted"
assert new[0].count("::Eden::BufferPages::NeverRegistered(addr, size)") == 2
assert "bool buffer_may_overlap = false;" in new[0]
assert "if (buffer_may_overlap)" in new[0]

original = methods(pinned)
assert new != original
assert new[0].count("::Eden::ImagePages::NeverHeld(addr, size)") == 3
assert new[1].count("::Eden::ImagePages::NeverHeld(addr, size)") == 1
assert "bool texture_may_overlap = false;" in new[0]
assert "Recheck under the texture mutex" in new[0]
assert "if (texture_may_overlap)" in new[0]
assert "R: skip provably unnecessary Vulkan texture-cache invalidation locks" in oracle
assert oracle.count("texture_may_overlap = false;") == 1
assert "Recheck under the texture mutex" in oracle
for source in (raster, bridge):
    assert "void RasterizerVulkan::InnerInvalidation(" in source
    assert source.index("if (texture_may_overlap)") < source.index(
        "std::scoped_lock lock{texture_cache.mutex};", source.index("if (texture_may_overlap)"))
    assert source.count("pipeline_cache.InvalidateRegion(addr, size);") >= 2

real_methods = (start + new[0] + end0 + new[1])
code = r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <mutex>
#include <span>
#include <utility>
#include "image_pages.h"
#include "buffer_pages.h"
using DAddr = std::uint64_t;
using u64 = std::uint64_t;
namespace VideoCommon {
enum class CacheType : unsigned { TextureCache = 1, BufferCache = 2,
                                  QueryCache = 4, ShaderCache = 8 };
}
constexpr VideoCommon::CacheType operator&(VideoCommon::CacheType a, VideoCommon::CacheType b) {
    return static_cast<VideoCommon::CacheType>(static_cast<unsigned>(a) & static_cast<unsigned>(b));
}
constexpr bool True(VideoCommon::CacheType which) { return static_cast<unsigned>(which) != 0; }
struct CountingMutex {
    std::mutex m;
    int locks{};
    std::function<void()> before_lock;
    void lock() {
        // Deterministically model image registration after batch precheck
        // but before acquiring the cache lock.
        if (before_lock) {
            auto publish = std::move(before_lock);
            before_lock = {};
            publish();
        }
        m.lock();
        ++locks;
    }
    void unlock() { m.unlock(); }
};
struct Cache {
    CountingMutex mutex;
    int writes{};
    void WriteMemory(DAddr, u64) { ++writes; }
};
struct QueryCache {
    int writes{};
    void InvalidateRegion(DAddr, u64) { ++writes; }
};
struct PipelineCache {
    int writes{};
    void InvalidateRegion(DAddr, u64) { ++writes; }
};
class RasterizerVulkan {
public:
    Cache texture_cache, buffer_cache;
    QueryCache query_cache;
    PipelineCache pipeline_cache;
    void InvalidateRegion(DAddr, u64, VideoCommon::CacheType);
    void InnerInvalidation(std::span<const std::pair<DAddr, std::size_t>>);
    void OnCacheInvalidation(DAddr, u64);
};
__EXTRACT__
int main() {
    constexpr u64 p = 4096;
    using namespace Eden;
    RasterizerVulkan x;
    const auto all = static_cast<VideoCommon::CacheType>(15);
    const auto tex = VideoCommon::CacheType::TextureCache;
    // Never-owned range: only texture lock/write can be suppressed.
    x.InvalidateRegion(10*p, p, all);
    assert(x.texture_cache.mutex.locks == 0 && x.texture_cache.writes == 0);
    assert(x.buffer_cache.mutex.locks == 1 && x.buffer_cache.writes == 1);
    assert(x.query_cache.writes == 1 && x.pipeline_cache.writes == 1);
    x.InvalidateRegion(0, p, all);
    x.InvalidateRegion(10*p, 0, all);
    assert(x.pipeline_cache.writes == 1 && x.texture_cache.mutex.locks == 0);

    ImagePages::Mark(20*p, p);
    BufferPages::Mark(20*p, p); // Independently registered GPU buffer
    x.InvalidateRegion(20*p, p, tex);
    x.InvalidateRegion(19*p, 2*p, tex);
    assert(x.texture_cache.mutex.locks == 2 && x.texture_cache.writes == 2);
    x.InvalidateRegion(60*p, 256*1024+1, tex);
    x.InvalidateRegion(ImagePages::kSpace - 2, 4, tex);
    assert(x.texture_cache.mutex.locks == 4 && x.texture_cache.writes == 4);

    // OnCacheInvalidation keeps buffer and shader notifications regardless.
    x.OnCacheInvalidation(40*p, p);
    assert(x.texture_cache.mutex.locks == 4 && x.texture_cache.writes == 4);
    assert(x.buffer_cache.writes == 2 && x.pipeline_cache.writes == 2);
    x.OnCacheInvalidation(20*p, p);
    assert(x.texture_cache.mutex.locks == 5 && x.texture_cache.writes == 5);
    assert(x.buffer_cache.writes == 3 && x.pipeline_cache.writes == 3);
    x.OnCacheInvalidation(0, p);
    assert(x.buffer_cache.writes == 3 && x.pipeline_cache.writes == 3);

    // Entirely unregistered batches skip both GPU cache locks; query/shader remain.
    std::array<std::pair<DAddr, std::size_t>, 2> clean{{
        {100*p, p}, {110*p, p}
    }};
    x.InnerInvalidation(clean);
    assert(x.texture_cache.mutex.locks == 5 && x.texture_cache.writes == 5);
    assert(x.buffer_cache.writes == 3 && x.query_cache.writes == 3);
    assert(x.buffer_cache.mutex.locks == 3);
    assert(x.pipeline_cache.writes == 5);

    // A mixed batch keeps the mutex but skips image-free individual ranges.
    std::array<std::pair<DAddr, std::size_t>, 2> mixed{{
        {120*p, p}, {20*p, p}
    }};
    x.InnerInvalidation(mixed);
    assert(x.texture_cache.mutex.locks == 6 && x.texture_cache.writes == 6);
    assert(x.buffer_cache.writes == 4 && x.query_cache.writes == 5);
    assert(x.buffer_cache.mutex.locks == 4);
    assert(x.pipeline_cache.writes == 7);

    // An unknown/large range still gets texture invalidation, unlike a
    // separate provably unowned page in the same mixed batch.
    std::array<std::pair<DAddr, std::size_t>, 2> uncertain{{
        {130*p, p}, {140*p, 256*1024+1}
    }};
    x.InnerInvalidation(uncertain);
    assert(x.texture_cache.mutex.locks == 7 && x.texture_cache.writes == 7);
    assert(x.buffer_cache.writes == 5 && x.query_cache.writes == 7);
    assert(x.buffer_cache.mutex.locks == 5);
    assert(x.pipeline_cache.writes == 9);
    // A concurrent registration can publish its monotonic page bit after
    // the outer mixed-batch scan, before we own the texture mutex.
    // The inner check MUST observe it and keep its invalidation.
    x.texture_cache.mutex.before_lock = [&] { ImagePages::Mark(150*p, p); };
    std::array<std::pair<DAddr, std::size_t>, 2> newly_registered{{
        {150*p, p}, {20*p, p}
    }};
    x.InnerInvalidation(newly_registered);
    assert(x.texture_cache.mutex.locks == 8 && x.texture_cache.writes == 9);
    assert(x.buffer_cache.writes == 6 && x.query_cache.writes == 9);
    assert(x.buffer_cache.mutex.locks == 6);
    assert(x.pipeline_cache.writes == 11);
    // Buffer registration may publish after the outer scan but before
    // acquiring the buffer lock in a mixed batch. Recheck under the mutex.
    x.buffer_cache.mutex.before_lock = [&] { BufferPages::Mark(160*p, p); };
    std::array<std::pair<DAddr, std::size_t>, 2> newly_registered_buffer{{
        {160*p, p}, {20*p, p}
    }};
    x.InnerInvalidation(newly_registered_buffer);
    assert(x.buffer_cache.writes == 8 && x.query_cache.writes == 11);
    assert(x.pipeline_cache.writes == 13);
    assert(x.buffer_cache.mutex.locks == 7);
    assert(x.texture_cache.mutex.locks == 9);
    std::array<std::pair<DAddr, std::size_t>, 0> empty{};
    x.InnerInvalidation(empty);
    assert(x.texture_cache.mutex.locks == 9 && x.buffer_cache.writes == 8);
    assert(x.buffer_cache.mutex.locks == 7);
}
""".replace("__EXTRACT__", real_methods)
compiler = shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "Clang required for ASan/UBSan source-extracted C++ witness"
with tempfile.TemporaryDirectory(prefix="encore-invalidation-elision-") as td:
    source = Path(td) / "invalidation.cpp"
    binary = Path(td) / "test"
    source.write_text(code)
    subprocess.run([compiler, "-std=c++20", "-O1", "-pthread",
                    "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-I"+str(root/"headless"),
                    str(source), "-o", str(binary)], check=True, timeout=55)
    subprocess.run([str(binary)], check=True, timeout=20)
print("VULKAN_TEXTURE_INVALIDATION_ELISION_HOST_PASS real_methods=3 "
      "never_registered=1 known=1 mixed_batch=1 oversized=1 out_of_range=1 "
      "all_other_caches_preserved=1 concurrent_registration=1 asan_ubsan=1")
