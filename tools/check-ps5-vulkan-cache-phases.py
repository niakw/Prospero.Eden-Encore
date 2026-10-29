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
# R361: all early exit paths are counted with zero successful-draw atomics.
p = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
graphics = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
assert "enum class GraphicsDrawDrop : unsigned" in perf
assert "if (!detailed_gpu_profile.load(std::memory_order_relaxed)) return;" in perf
assert "graphics_draw_drop_totals" in perf
assert "EDEN_GPU_DRAW_DROP frame=%u reason=%s total=%llu window=%llu" in report
assert "GraphicsDrawDrop::NoPipeline" in p
assert "GraphicsDrawDrop::ConfigureRejected" in p
assert "GraphicsDrawDrop::BuiltPipelineFailed" in graphics
assert "GraphicsDrawDrop::DescriptorBufferFull" in graphics
assert "GraphicsDrawDrop::WorkerPipelineFailed" in graphics
assert "GraphicsDrawDrop::WorkerPipelineFailed" in generator
assert "WorkerPipelineFailed" in perf
assert '"worker_pipeline_failed"' in report
# F07 P0.2 worker waits are distinct from cold CPU shader translation.
for phase, label, native in (
    ("GraphicsPipelineWait", "graphics_pipeline_wait", "vk_graphics_pipeline_cost.cpp"),
    ("ComputePipelineWait", "compute_pipeline_wait", "vk_compute_pipeline_cost.cpp"),
):
    assert phase in perf
    assert report.count('"' + label + '"') == 1
    selected = (root / "vendor/encore-active/eden-vulkan" / native).read_text()
    site = selected.index("scheduler.Record([this](vk::CommandBuffer) {")
    callback = selected[site:selected.index("        });", site)]
    assert callback.index("if (is_built.load(std::memory_order_acquire)) return;") < callback.index("CachePhase::" + phase) < callback.index("std::unique_lock lock{build_mutex};")
    assert callback.count("detailed_gpu_profile.load(std::memory_order_relaxed)") == 1
    assert "wait_phase = 'GraphicsPipelineWait' if name" in generator

assert "GraphicsDrawDrop::DescriptorBufferFull" in generator
assert "GraphicsDrawDrop::ConfigureRejected" in generator
# R362 uses 1-in-16 timers without altering the guest cache lock lifetimes.
p = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
for phase in ("StageTextureHandles", "BindTextureBuffers", "BindStageDescriptors",
              "StageHostBuffers", "StageImageDescriptors",
              "RefreshRenderTargets", "CheckFeedbackLoop", "CommitGraphicsDraw"):
    assert "CachePhase::" + phase in p
    assert "CachePhase::" + phase in generator
    assert phase in perf
assert "stage_texture_phase.Stop();" in p
assert "bind_texture_phase.Stop();" in p
assert "stage_descriptor_phase.Stop();" in p
# These costs are nested inside BindStageDescriptors, so their sums must
# never be reported as independent extra time.
assert p.count("CachePhase::StageHostBuffers") == 1
assert p.count("CachePhase::StageImageDescriptors") == 1
assert p.index("CachePhase::StageHostBuffers") < p.index(
    "buffer_cache.BindHostStageBuffers(stage);") < p.index(
    "CachePhase::StageImageDescriptors") < p.index(
    "PushImageDescriptors(texture_cache, guest_descriptor_queue, info, rescaling,")
assert "apply_reviewed_delta(pipeline," in generator
assert "'F01 isolate image descriptor push cost within stage binding'" in generator
for label in ("stage_texture_handles", "bind_texture_buffers", "bind_stage_descriptors",
              "stage_host_buffers", "stage_image_descriptors",
              "refresh_render_targets", "check_feedback_loop", "commit_graphics_draw"):
    assert '"' + label + '"' in report
assert "return ConfigureDraw(rescaling, render_area);" in p
assert "std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};" in generator
assert "pipeline->Configure(is_indexed)" in generator
assert "cache_draw_sample_active = previous_sample;" in generator
assert "if (!pipeline_ok)" in generator
assert "return;" in generator
assert "Eden::Performance::ResetCachePhases();" in main
assert ("EDEN_GPU_CACHE_PHASE frame=%u phase=%s samples=%llu total_ns=%llu "
        "window_samples=%llu window_ns=%llu max_ns=%llu") in report
assert "samples >= last_samples[phase] ? samples - last_samples[phase] : samples" in report
assert "total_ns >= last_total_ns[phase] ? total_ns - last_total_ns[phase] : total_ns" in report
assert "entry.max_ns.exchange(0, std::memory_order_relaxed)" in report
assert "auto& entry = cache_phase_totals[phase];" in report
assert "const auto& entry = cache_phase_totals[phase];" not in report
# The detailed-only R393 IPC thread rows now sit between the guest summary
# and the sampled cache phase report. Validate semantic ordering, not brittle
# adjacency to the previous printf closing line.
assert report.index('EDEN_DEV_GUEST cpu_write_calls=') < report.index(
    '    // These are 1-in-16') < report.index(
    'const auto window = Eden::Fastmem::WindowStats();')
assert report.index('EDEN_DEV_IPC_THREAD tid=') < report.index(
    '    // These are 1-in-16')
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
#include <cstdio>
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

# R355: the exact active renderer's cached storage must be isolated per thread
# and safe for nested/reentrant ConfigureImpl calls.
active = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
assert "GraphicsDescriptorScratchLease scratch;" in active
assert "std::optional<GraphicsDescriptorScratchLease> reused" not in active
assert "void GraphicsPipeline::PreflightDescriptorScratch()" in active
assert "scratch.views.reserve(num_image_elements)" in active
assert "scratch.samplers.reserve(num_textures)" in active
assert "thread_local GraphicsDescriptorScratch graphics_descriptor_nested_scratch;" in active
assert "graphics_descriptor_nested_scratch" in generator
assert "if (!nested) current->in_use = false;" in active
header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
rasterizer = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
assert "void PreflightDescriptorScratch();" in header
assert "pipeline->PreflightDescriptorScratch();" in rasterizer
assert rasterizer.index("pipeline->PreflightDescriptorScratch();") < rasterizer.index(
    "std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};")
assert "pipeline->PreflightDescriptorScratch();" in generator
assert "GraphicsDescriptorScratchLease scratch;" in generator
start = active.index("struct GraphicsDescriptorScratch {")
stop = active.index("DescriptorLayoutBuilder MakeBuilder", start)
scratch_helper = active[start:stop]
scratch_cpp = r"""
#include <boost/container/small_vector.hpp>
#include <cassert>
#include <cstdint>
#include <memory>
#include <thread>
namespace VideoCommon {
struct ImageViewInOut {
    std::uint32_t index{};
    bool blacklist{};
    std::uint64_t id{};
};
using SamplerId = std::uint32_t;
}
namespace Vulkan {
namespace {
__SCRATCH_HELPER__
}
}
int main() {
    using Vulkan::GraphicsDescriptorScratchLease;
    std::size_t saved_capacity = 0;
    {
        GraphicsDescriptorScratchLease outer;
        assert(outer.Views().empty());
        for (unsigned i = 0; i < 130; ++i) {
            outer.Views().push_back({i, false, i});
            outer.Samplers().push_back(i);
        }
        saved_capacity = outer.Views().capacity();
        {
            GraphicsDescriptorScratchLease nested;
            assert(nested.Views().empty());
            assert(&nested.Views() == &Vulkan::graphics_descriptor_nested_scratch.views);
            nested.Views().push_back({999, true, 42});
            assert(nested.Views()[0].index == 999);
            {
                GraphicsDescriptorScratchLease deep;
                assert(&deep.Views() != &nested.Views());
                deep.Views().push_back({888, false, 88});
                assert(deep.Views().front().index == 888);
                assert(nested.Views()[0].index == 999);
            }
        }
        {
            GraphicsDescriptorScratchLease reused_nested;
            assert(reused_nested.Views().empty());
            assert(&reused_nested.Views() == &Vulkan::graphics_descriptor_nested_scratch.views);
        }
        assert(outer.Views().size() == 130);
        assert(outer.Views()[129].index == 129);
        assert(outer.Samplers()[129] == 129);
    }
    {
        GraphicsDescriptorScratchLease next;
        assert(next.Views().empty() && next.Samplers().empty());
        assert(next.Views().capacity() >= saved_capacity);
    }
    std::thread guest([] {
        GraphicsDescriptorScratchLease other_thread;
        assert(other_thread.Views().empty());
        other_thread.Views().push_back({1234, false, 7});
    });
    guest.join();
    GraphicsDescriptorScratchLease main_thread;
    assert(main_thread.Views().empty());
}
""".replace("__SCRATCH_HELPER__", scratch_helper)
with tempfile.TemporaryDirectory(prefix="eden-r355-scratch-") as d:
    source = Path(d) / "scratch.cpp"
    binary = Path(d) / "scratch"
    source.write_text(scratch_cpp)
    subprocess.run([compiler, "-std=c++20", "-O1", "-Wall", "-Wextra",
                    "-Werror", "-pthread", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS R355: graphics descriptor scratch reuses capacity, isolates nested calls and threads")

# R360: exact rare under-lock ring exhaustion versus sampled ConfigureDraw.
ring = (root / "vendor/encore-active/eden-vulkan/vk_descriptor_buffer_cost.cpp").read_text()
assert "DescriptorRingFinish" in perf
assert '"descriptor_ring_finish"' in report
assert "CachePhase::DescriptorRingFinish" in ring
assert "CachePhase::DescriptorRingFinish" in generator
assert "CachePhase::DescriptorRingPreflight" in generator
assert "CachePhase::DescriptorRingPreflight" in ring
assert '"descriptor_ring_preflight"' in report
assert "detailed_gpu_profile.load(std::memory_order_relaxed)" in ring
assert ring.index("CachePhase::DescriptorRingFinish") < ring.index("scheduler.Finish();", ring.index("CachePhase::DescriptorRingFinish"))
assert "chunk_cursor = 0;" in ring and "++generation;" in ring
