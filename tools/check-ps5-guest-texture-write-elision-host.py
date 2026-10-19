#!/usr/bin/env python3
"""Native-source-extracted guest CPU-write cache-lock elision regression.

ASan/UBSan host witness. Only never-held texture pages skip the texture
mutex; shader invalidation remains independent and unchanged.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
raster = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
cache = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
oracle = (root / "tools/prepare-vulkan-port.py").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
begin = raster.index("bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {")
end = raster.index("\nvoid RasterizerVulkan::OnCacheInvalidation(", begin)
body = raster[begin:end]
assert body.count("::Eden::ImagePages::NeverHeld(addr, size)") == 1
assert body.count("::Eden::BufferPages::NeverRegistered(addr, size)") == 1
assert body.count("pipeline_cache.InvalidateRegion(addr, size);") == 1
assert body.index("if (!::Eden::ImagePages::NeverHeld(addr, size))") < body.index(
    "texture_cache.WriteMemory(addr, size)")
assert body.index("texture_cache.WriteMemory(addr, size)") < body.index(
    "pipeline_cache.InvalidateRegion(addr, size)")
assert cache.index("::Eden::ImagePages::Mark(image.cpu_addr") < cache.index(
    "slot_map_views.insert(image.gpu_addr")
assert cache.index("::Eden::ImagePages::Mark(cpu_addr, size)") < cache.index(
    "slot_map_views.insert(gpu_addr, cpu_addr")
assert oracle.count("if (!::Eden::ImagePages::NeverHeld(addr, size))") == 4
assert "python3 -B tools/check-ps5-guest-texture-write-elision-host.py" in workflow

cpp = r"""
#include <atomic>
#include <cassert>
#include <cstdint>
#include <mutex>
#include "image_pages.h"
#include "buffer_pages.h"
#include "buffer_write_ahead.h"
using DAddr = std::uint64_t;
using u64 = std::uint64_t;
#define DEBUG_ASSERT(expr) assert(expr)
namespace Eden::Performance {
enum class CachePhase {
    GuestWriteBufferWait, GuestWriteBufferWork,
    GuestWriteTextureWait, GuestWriteTextureWork,
    GuestWriteShaderInvalidate
};
struct BatchedGuestWriteTimer { ~BatchedGuestWriteTimer() {} };
struct CachePhaseTimer {
    CachePhaseTimer(CachePhase, bool) {}
    void Stop() {}
};
inline std::atomic<unsigned> cpu_write_ahead{0};
inline std::atomic<unsigned> texture_lock_calls{0};
bool ShouldSampleGuestWrite() { return false; }
void GuestCacheLock(std::recursive_mutex& mutex, bool texture) {
    if (texture) ++texture_lock_calls;
    mutex.lock();
}
}
struct MockBuffer {
    std::recursive_mutex mutex;
    bool early_exit{false};
    unsigned writes{0};
    bool OnCPUWrite(DAddr, u64) { ++writes; return early_exit; }
    bool IsRegionRegistered(DAddr, u64) { return true; }
};
struct MockTexture {
    std::recursive_mutex mutex;
    unsigned writes{0};
    void WriteMemory(DAddr, u64) { ++writes; }
};
struct MockPipeline {
    unsigned writes{0};
    void InvalidateRegion(DAddr, u64) { ++writes; }
};
class RasterizerVulkan {
public:
    MockBuffer buffer_cache;
    MockTexture texture_cache;
    MockPipeline pipeline_cache;
    bool OnCPUWrite(DAddr addr, u64 size);
};
__REAL_METHOD__
int main() {
    using namespace Eden;
    constexpr u64 page = 4096;
    RasterizerVulkan r;
    const auto write = [&](u64 addr, u64 size) { return r.OnCPUWrite(addr, size); };

    // No texture was registered: skip its mutex, but always invalidate shaders.
    assert(!write(100 * page, page));
    assert(r.texture_cache.writes == 0);
    assert(Performance::texture_lock_calls == 0);
    assert(r.pipeline_cache.writes == 1 && r.buffer_cache.writes == 0);

    // Once a texture ever occupied a page, the conservative locked path sticks.
    ImagePages::Mark(200 * page, page);
    assert(!write(200 * page, page));
    assert(!write(200 * page, page));
    assert(r.texture_cache.writes == 2);
    assert(Performance::texture_lock_calls == 2);
    assert(r.pipeline_cache.writes == 3);

    // Range spanning a formerly registered page cannot be skipped.
    assert(!write(199 * page, 2 * page));
    assert(r.texture_cache.writes == 3);
    assert(Performance::texture_lock_calls == 3);

    // Large / out-of-range writes must always use the original locked route.
    assert(!write(300 * page, 256 * 1024 + 1));
    assert(!write(ImagePages::kSpace, page));
    assert(r.texture_cache.writes == 5);
    assert(Performance::texture_lock_calls == 5);
    assert(r.pipeline_cache.writes == 6);
    // Above-cap and out-of-range writes intentionally fall back to the
    // original BUFFER mutex as well; count them separately from textures.
    assert(r.buffer_cache.writes == 2);

    // Buffer and texture ownership are independent evidence domains.
    BufferPages::Mark(400 * page, page);
    assert(!write(400 * page, page));
    assert(r.buffer_cache.writes == 3);
    assert(r.texture_cache.writes == 5);
    assert(r.pipeline_cache.writes == 7);

    // Original early-exit semantics: no downstream texture/shader invalidation.
    r.buffer_cache.early_exit = true;
    BufferPages::Mark(500 * page, page);
    assert(write(500 * page, page));
    assert(r.buffer_cache.writes == 4);
    assert(r.texture_cache.writes == 5);
    assert(r.pipeline_cache.writes == 7);
}
""".replace("__REAL_METHOD__", body)
compiler = shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "Clang required for ASan/UBSan native method witness"
with tempfile.TemporaryDirectory(prefix="encore-cpuwrite-image-elision-") as temp:
    source = Path(temp) / "cpu-write.cpp"
    binary = Path(temp) / "test"
    source.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O1", "-pthread", "-Wall",
                    "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-I" + str(root / "headless"),
                    str(source), "-o", str(binary)], check=True, timeout=55)
    subprocess.run([str(binary)], check=True, timeout=20)
print("CPU_WRITE_TEXTURE_ELISION_HOST_PASS real_method=1 unowned_skip=1 "
      "registered_invalidation=1 range_overlap=1 fail_closed=1 "
      "buffer_independent=1 shader_always=1 early_exit=1 sanitizer=1")
