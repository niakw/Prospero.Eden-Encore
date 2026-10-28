#!/usr/bin/env python3
"""Execute the selected native pipeline-aware descriptor preflight with mock queues."""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
b=src.index("    GraphicsPipeline* pipeline{pipeline_cache.CurrentGraphicsPipeline()};")
e=src.index("#ifdef PS5_NATIVE\n    // Waiting on an eight-frame-old",b)
selected=src[b:e]
assert "pipeline->HasDescriptorEntries()" in selected
assert selected.count("pipeline_cache.CurrentGraphicsPipeline()") == 3
assert "guest_descriptor_queue.PreflightGuestDraw(" in selected
assert "if (preflight == 0 && !initial_descriptor_drain) break;" in selected
assert "guest_descriptor_queue.PreflightExactGuestDraw(" in selected
assert "pipeline->DescriptorEntryReservation()))" in selected
assert selected.index("pipeline->HasDescriptorEntries()") < selected.index("PreflightGuestDraw(")
assert selected.index("gpu_memory->FlushCaching();") > selected.index("PreflightGuestDraw(")
assert selected.count("GraphicsDrawDrop::NoPipeline") == 3
header=(root/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
assert header.count("bool HasDescriptorEntries() const noexcept") == 1
assert "return num_descriptor_entries != 0;" in header
oracle=(root/"tools/prepare-vulkan-port.py").read_text()
assert "Source-selected graphics preflight" in oracle
assert "bool HasDescriptorEntries() const noexcept" in oracle
fixture=r"""
#include <cassert>
#include <cstddef>
namespace Eden::Performance {
enum class GraphicsDrawDrop { NoPipeline };
inline unsigned dropped = 0;
void RecordGraphicsDrawDrop(GraphicsDrawDrop) { ++dropped; }
}
struct GraphicsPipeline {
    std::size_t entries{};
    bool HasDescriptorEntries() const noexcept { return entries != 0; }
    std::size_t DescriptorEntryReservation() const noexcept {
        return entries == 0 ? 0x400 : entries;
    }
};
struct PipelineCache {
    GraphicsPipeline* selected{};
    GraphicsPipeline* after_drain{};
    unsigned selects{};
    GraphicsPipeline* CurrentGraphicsPipeline() {
        ++selects;
        return selects == 1 || !after_drain ? selected : after_drain;
    }
};
struct Scheduler {
    unsigned waits{};
    void WaitWorker() { ++waits; }
};
struct GpuMemory {
    unsigned flushes{};
    void FlushCaching() { ++flushes; }
};
struct DescriptorQueue {
    bool full{};
    unsigned checks{};
    template <class F>
    bool PreflightGuestDraw(F&& worker, std::size_t required_entries) {
        assert(required_entries != 0 && required_entries < 0x400);
        ++checks;
        if (!full) return false;
        full = false;
        worker();
        return true;
    }
    unsigned exact_checks{};
    template <class F>
    bool PreflightExactGuestDraw(F&& worker, std::size_t required_entries) {
        assert(required_entries != 0 && required_entries < 0x400);
        ++exact_checks;
        if (!full) return false;
        full = false;
        worker();
        return true;
    }
};
struct Rasterizer {
    PipelineCache pipeline_cache;
    Scheduler scheduler;
    DescriptorQueue guest_descriptor_queue;
    GpuMemory memory;
    GpuMemory* gpu_memory = &memory;
    void Test() {
""" + selected + r"""
    }
};
int main() {
    GraphicsPipeline empty{0};
    GraphicsPipeline textured{8};
    Rasterizer x;
    x.pipeline_cache.selected = &empty;
    x.guest_descriptor_queue.full = true;
    x.Test();
    assert(x.scheduler.waits == 0 && x.guest_descriptor_queue.checks == 0);
    assert(x.pipeline_cache.selects == 1 && x.memory.flushes == 0);
    Rasterizer y;
    y.pipeline_cache.selected = &textured;
    y.guest_descriptor_queue.full = true;
    y.pipeline_cache.after_drain = &empty;
    y.Test();
    assert(y.scheduler.waits == 1 && y.memory.flushes == 1);
    assert(y.pipeline_cache.selects == 2);
    // A drain reselected a descriptor-free pipeline: no exact probe is needed.
    assert(y.guest_descriptor_queue.exact_checks == 0);
    Rasterizer z;
    z.pipeline_cache.selected = &textured;
    z.guest_descriptor_queue.full = true;
    z.pipeline_cache.after_drain = nullptr;
    z.Test();
    assert(z.scheduler.waits == 1 && z.pipeline_cache.selects == 2);
    assert(z.guest_descriptor_queue.exact_checks == 1);
    Rasterizer n;
    n.pipeline_cache.selected = nullptr;
    n.Test();
    assert(n.scheduler.waits == 0 && Eden::Performance::dropped == 1);
    Rasterizer unchanged;
    unchanged.pipeline_cache.selected = &textured;
    unchanged.Test();
    assert(unchanged.guest_descriptor_queue.checks == 1);
    assert(unchanged.guest_descriptor_queue.exact_checks == 0);
    assert(unchanged.scheduler.waits == 0 && unchanged.pipeline_cache.selects == 1);
}
"""
with tempfile.TemporaryDirectory(prefix="encore-preflight-pipeline-") as d:
    source=Path(d)/"test.cpp"
    source.write_text(fixture)
    for opt in ("-O0","-O2"):
        exe=Path(d)/opt
        subprocess.run(["c++","-std=c++20",opt,"-Wall","-Wextra","-Werror",
                        "-DPS5_NATIVE",str(source),"-o",str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
        print("PIPELINE_AWARE_DESCRIPTOR_PREFLIGHT_PASS",opt)
