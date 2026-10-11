#!/usr/bin/env python3
"""R310: ensure cache-phase diagnostic sampling does not change GPU cache ownership."""
import ast
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
generator = (root / "tools/prepare-vulkan-port.py").read_text()
perf = (root / "headless/performance.h").read_text()
report = (root / "headless/performance.cpp").read_text()
main = (root / "headless/main.cpp").read_text()
ast.parse(generator)
assert "std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};" in generator
assert "pipeline->Configure(is_indexed)" in generator
assert "cache_draw_sample_active = previous_sample;" in generator
assert "if (!pipeline_ok)" in generator
assert "return;" in generator
assert "Eden::Performance::ResetCachePhases();" in main
assert "EDEN_GPU_CACHE_PHASE frame=%u phase=%s samples=%llu total_ns=%llu max_ns=%llu" in report
assert "entry.max_ns.exchange(0, std::memory_order_relaxed)" in report
assert report.index('std::printf("\\n");\n    // These are 1-in-16') < report.index(
    'const auto window = Eden::Fastmem::WindowStats();')
for name in ("PairWait", "PairHeld", "PipelineConfigure", "TextureDescriptorSync",
             "TextureFillImageViews", "GraphicsBufferUpdate", "DescriptorQueueAcquire",
             "DynamicStates", "QueryAndDraw"):
    assert name in perf
    assert name in generator
assert generator.count("CachePhaseTimer") >= 6  # five outer sites plus four loop-generated inner stages
# The configuration cache tasks are timed INSIDE the existing dual lock,
# with no new unlock, queue flush, pipeline skip or GPU hazard.
assert "std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};" in generator
assert "buffer_cache.UpdateGraphicsBuffers(is_indexed);" in generator
assert "texture_cache.FillImageViews(std::span(views.data(), views.size()), false, Spec::has_images);" in generator

begin = perf.index("enum class CachePhase : unsigned {")
end = perf.index("// Guest waits: nvhost_ctrl", begin)
extracted = perf[begin:end]
cpp = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <thread>
namespace Common {
struct Clock {
 std::chrono::nanoseconds GetTimeNS() const noexcept {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::steady_clock::now().time_since_epoch());
 }
};
inline Clock g_wall_clock;
}
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{false};
__EXTRACTED__
}
int main() {
 using namespace Eden::Performance;
 for (unsigned i=0;i<48;++i) assert(!ShouldSampleCacheDraw());
 detailed_gpu_profile.store(true);
 unsigned chosen=0;
 for (unsigned i=0;i<64;++i) if (ShouldSampleCacheDraw()) ++chosen;
 assert(chosen==4);
 assert(!cache_draw_sample_active);
 {
  CachePhaseTimer disabled(CachePhase::PairWait);
  std::this_thread::sleep_for(std::chrono::microseconds(5));
 }
 assert(cache_phase_totals[0].samples.load() == 0);
 cache_draw_sample_active=true;
 {
  CachePhaseTimer timer(CachePhase::PairWait);
  std::this_thread::sleep_for(std::chrono::microseconds(5));
  timer.Stop();
  timer.Stop();
 }
 assert(cache_phase_totals[0].samples.load()==1);
 assert(cache_phase_totals[0].total_ns.load()>0);
 assert(cache_phase_totals[0].max_ns.load()>0);
 ResetCachePhases();
 assert(cache_phase_totals[0].samples.load()==0);
 assert(cache_phase_totals[0].total_ns.load()==0);
 assert(cache_phase_totals[0].max_ns.load()==0);
}
""".replace("__EXTRACTED__",extracted)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "Host C++ compiler required"
with tempfile.TemporaryDirectory(prefix="eden-r310-vk-cache-") as d:
    source=Path(d)/"cache_probe.cpp"
    binary=Path(d)/"cache_probe"
    source.write_text(cpp)
    subprocess.run([compiler, "-std=c++20","-O1","-Wall","-Wextra","-Werror",
                    "-pthread",str(source),"-o",str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print("PASS R310: cache hotpath sample 1/16, max/delta/reset/quiet, pinned locks preserved")
