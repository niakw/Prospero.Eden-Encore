#!/usr/bin/env python3
"""F07 C03: compile real TextureCache::TickFrame and phase timer with two modes.

Host-only: checks preservation of event ordering, exact budget/GC
instrumentation, 1-in-16 async/runtime samples, quiet path, and native-only
conditional behavior. No game/driver latency claims.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import json

root = Path(__file__).resolve().parents[1]
source = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
perf = (root / "headless/performance.h").read_text()
reporter = (root / "headless/performance.cpp").read_text()
marker = "void TextureCache<P>::TickFrame() {"
start = source.index(marker)
end = source.index("\n}\n", start) + 2
real_tick = source[start:end]
assert json.dumps(real_tick, ensure_ascii=False) in generator
assert generator.count("F07 texture frame GC and driver probe phase attribution") == 1
assert source.count("::Eden::Performance::CachePhase::TextureBudgetQuery") == 1
assert source.count("::Eden::Performance::CachePhase::TextureGcCollect") == 1
assert source.count("::Eden::Performance::CachePhase::TextureAsyncTick") == 1
assert source.count("::Eden::Performance::CachePhase::TextureRuntimeTick") == 1
assert reporter.count('"texture_budget_query"') == 1
assert reporter.count('"texture_gc_collect"') == 1
assert reporter.count('"texture_async_tick"') == 1
assert reporter.count('"texture_runtime_tick"') == 1
assert "ShouldSampleTextureHousekeeping()" in perf
assert real_tick.index("runtime.GetDeviceMemoryUsage()") < real_tick.index("RunGarbageCollector()")
assert real_tick.index("RunGarbageCollector()") < real_tick.index("TickAsyncDecode()")
assert real_tick.index("TickAsyncDecode()") < real_tick.index("TickAsyncUnswizzle()")
assert real_tick.index("TickAsyncUnswizzle()") < real_tick.index("runtime.TickFrame()")
assert real_tick.index("runtime.TickFrame()") < real_tick.index("++frame_tick;")

begin = perf.index("enum class CachePhase : unsigned {")
finish = perf.index("// V01:", begin)
phase_source = perf[begin:finish]
assert "class CachePhaseTimer" in phase_source
assert "inline bool ShouldSampleTextureHousekeeping()" in phase_source

code = r"""
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <vector>
using u64 = std::uint64_t;
namespace Common {
struct Clock {
    std::chrono::nanoseconds GetTimeNS() const {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch());
    }
};
inline Clock g_wall_clock;
}
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{false};
__PHASE_SOURCE__
}
struct Runtime {
    int available_usage = 100;
    unsigned queries = 0;
    bool report_usage = true;
    bool CanReportMemoryUsage() const noexcept { return report_usage; }
    int GetDeviceMemoryUsage() { ++queries; return available_usage; }
    unsigned frames = 0;
    void TickFrame() { ++frames; }
    void FreeDeferredStagingBuffer(int) {}
};
struct Retire {
    unsigned count = 0;
    void Tick() { ++count; }
};
template<class P>
class TextureCache {
public:
    static constexpr bool IMPLEMENTS_ASYNC_DOWNLOADS = false;
    Runtime runtime;
    int total_used_memory = 0;
    int minimum_memory = 1000;
    unsigned long long frame_tick = 0;
    unsigned gc = 0, async_decode = 0, async_unswizzle = 0;
    Retire sentenced_images, sentenced_framebuffers, sentenced_image_view;
    std::vector<int> async_buffers_death_ring{};
    void TickFrame();
    void RunGarbageCollector() { ++gc; }
    void TickAsyncDecode() { ++async_decode; }
    void TickAsyncUnswizzle() { ++async_unswizzle; }
};
template<class P>
__REAL_TICK__
struct Tag {};
int main() {
    using namespace Eden::Performance;
    TextureCache<Tag> texture;
    auto calls = [](CachePhase p) {
        return cache_phase_totals[static_cast<unsigned>(p)].samples.load();
    };
    // Quiet path: the very same GPU bookkeeping still executes, but no
    // extra clocks/counters are sampled even during forced GC.
    for (int n = 0; n < 16; ++n) texture.TickFrame();
#ifdef PS5_NATIVE
    assert(texture.runtime.queries == 8);
#else
    assert(texture.runtime.queries == 16);
#endif
    assert(texture.gc == 0 && texture.frame_tick == 16);
    assert(calls(CachePhase::TextureBudgetQuery) == 0);
    assert(calls(CachePhase::TextureGcCollect) == 0);
    assert(calls(CachePhase::TextureAsyncTick) == 0);
    assert(calls(CachePhase::TextureRuntimeTick) == 0);
    detailed_gpu_profile.store(true);
    for (int n = 0; n < 16; ++n) texture.TickFrame();
#ifdef PS5_NATIVE
    assert(texture.runtime.queries == 16);
    assert(calls(CachePhase::TextureBudgetQuery) == 8);
    assert(calls(CachePhase::TextureAsyncTick) == 1);
    assert(calls(CachePhase::TextureRuntimeTick) == 1);
    assert(calls(CachePhase::TextureGcCollect) == 0);
#else
    assert(texture.runtime.queries == 32);
    assert(calls(CachePhase::TextureBudgetQuery) == 0);
#endif
    texture.runtime.available_usage = 2000;
    for (int n = 0; n < 16; ++n) texture.TickFrame();
#ifdef PS5_NATIVE
    // From an old, low-pressure snapshot the first eligible probe detects
    // pressure, then EVERY frame must probe/collect.
    assert(texture.runtime.queries == 32);
    assert(calls(CachePhase::TextureBudgetQuery) == 24);
    assert(calls(CachePhase::TextureGcCollect) == 16);
    assert(calls(CachePhase::TextureAsyncTick) == 2);
    assert(calls(CachePhase::TextureRuntimeTick) == 2);
    assert(texture.gc == 16);
#else
    assert(texture.gc == 16);
    assert(calls(CachePhase::TextureGcCollect) == 0);
#endif
    // The silent path keeps normal behavior without affecting sampled totals.
    detailed_gpu_profile.store(false);
    for (int n = 0; n < 16; ++n) texture.TickFrame();
#ifdef PS5_NATIVE
    assert(calls(CachePhase::TextureBudgetQuery) == 24);
    assert(calls(CachePhase::TextureGcCollect) == 16);
    assert(calls(CachePhase::TextureAsyncTick) == 2);
#else
    assert(calls(CachePhase::TextureBudgetQuery) == 0);
#endif
    assert(texture.frame_tick == 64);
    assert(texture.gc == 32);
    assert(texture.sentenced_images.count == 64);
    assert(texture.sentenced_framebuffers.count == 64);
    assert(texture.sentenced_image_view.count == 64);
    assert(texture.async_decode == 64 && texture.async_unswizzle == 64);
    assert(texture.runtime.frames == 64);
}
"""
code = code.replace("__PHASE_SOURCE__", phase_source).replace("__REAL_TICK__", real_tick)

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-texture-frame-phase-") as folder:
    path = Path(folder) / "texture.cpp"
    path.write_text(code)
    for native in (False, True):
        for optimize in ("-O0", "-O2"):
            exe = Path(folder) / f"{'ps5' if native else 'desktop'}-{optimize[1:]}"
            built = subprocess.run(
                [compiler, "-std=c++20", optimize, "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 *(["-DPS5_NATIVE=1"] if native else []),
                 str(path), "-o", str(exe)],
                capture_output=True, text=True, timeout=50,
            )
            assert built.returncode == 0, (native, optimize, built.stderr[-6000:])
            ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            assert ran.returncode == 0, (native, optimize, ran.stderr[-3500:])
            print(f"F07_TEXTURE_FRAME_GC_PHASE_PASS native={int(native)} {optimize} quiet=1 budget=1 gc=1 sampled_async=1 order=1")
print("HOST_ONLY: no FC27 latency, GPU VRAM or console FPS assertions")
