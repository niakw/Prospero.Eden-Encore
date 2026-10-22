#!/usr/bin/env python3
"""Execute source-selected PS5 compute descriptor-free dispatch and queue policy."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
raster = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
compute = (root / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()
header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_compute_pipeline.h").read_text()
oracle = (root / "tools/prepare-vulkan-port.py").read_text()
assert "bool HasDescriptorEntries() const noexcept" in header
assert "return num_descriptor_entries != 0;" in header
assert "Compute empty-descriptor native anchor changed" in oracle
dispatch = raster.split("void RasterizerVulkan::DispatchCompute() {", 1)[1]
initial = dispatch.index("    ComputePipeline* pipeline{pipeline_cache.CurrentComputePipeline()};")
end = dispatch.index("#ifdef PS5_NATIVE\n    // Compute always allocates", initial)
selection = dispatch[initial:end]
assert selection.count("pipeline->HasDescriptorEntries()") == 1
assert selection.count("pipeline_cache.CurrentComputePipeline()") == 2
assert selection.index("HasDescriptorEntries()") < selection.index("PreflightGuestDraw(")
assert "gpu_memory->FlushCaching();" in selection
configure = compute.split("bool ComputePipeline::Configure(", 1)[1]
initial = configure.index("    if (num_descriptor_entries == 0) {")
end = configure.index("\n\n    buffer_cache.SetComputeUniformBufferState", initial)
acquire = configure[initial:end]
assert acquire.count("AcquireKnownEmpty(uses_descriptor_buffer)") == 1
assert acquire.count("guest_descriptor_queue.Acquire(scheduler, num_descriptor_entries, uses_descriptor_buffer)") == 1
queue_header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_update_descriptor.h").read_text()
assert "void AcquireKnownEmpty(bool use_descriptor_buffer_) noexcept" in queue_header

test = r"""
#include <cassert>
#include <cstddef>
struct ComputePipeline {
    std::size_t entries{};
    bool HasDescriptorEntries() const noexcept { return entries != 0; }
};
struct Scheduler {
    unsigned waits{};
    void WaitWorker() { ++waits; }
};
struct PipelineCache {
    ComputePipeline* current{};
    ComputePipeline* after_wait{};
    bool has_after_wait{};
    unsigned lookups{};
    ComputePipeline* CurrentComputePipeline() {
        ++lookups;
        return lookups > 1 && has_after_wait ? after_wait : current;
    }
};
struct GPU {
    unsigned flushes{};
    void FlushCaching() { ++flushes; }
};
struct Queue {
    bool full{};
    unsigned checks{}, empties{}, acquires{};
    template<class W> bool PreflightGuestDraw(W&& worker) {
        ++checks;
        if (!full) return false;
        worker();
        return true;
    }
    void AcquireKnownEmpty(bool) { ++empties; }
    void Acquire(Scheduler& scheduler, std::size_t entries, bool) {
        ++acquires;
        if (entries == 0) scheduler.WaitWorker(); // legacy fallback, forbidden
    }
};
struct Rasterizer {
    ComputePipeline* pipeline{};
    PipelineCache pipeline_cache;
    GPU memory;
    GPU* gpu_memory=&memory;
    Scheduler scheduler;
    Queue guest_descriptor_queue;
    void Test() {
""" + selection + r"""
        this->pipeline = pipeline;
    }
};
struct Configuration {
    std::size_t num_descriptor_entries{};
    bool uses_descriptor_buffer{};
    Scheduler scheduler;
    Queue guest_descriptor_queue;
    void Apply() {
""" + acquire + r"""
    }
};
int main() {
    ComputePipeline empty{0}, populated{8};
    Rasterizer a;
    a.pipeline_cache.current = &empty;
    a.guest_descriptor_queue.full=true;
    a.Test();
    assert(a.pipeline==&empty && a.scheduler.waits==0);
    assert(a.guest_descriptor_queue.checks==0 && a.pipeline_cache.lookups==1);

    Rasterizer b;
    b.pipeline_cache.current=&populated;
    b.pipeline_cache.after_wait=&empty;
    b.pipeline_cache.has_after_wait=true;
    b.guest_descriptor_queue.full=true;
    b.Test();
    assert(b.scheduler.waits==1 && b.memory.flushes==1);
    assert(b.pipeline_cache.lookups==2 && b.pipeline==&empty);

    Rasterizer c;
    c.pipeline_cache.current=&populated;
    c.guest_descriptor_queue.full=false;
    c.Test();
    assert(c.scheduler.waits==0 && c.guest_descriptor_queue.checks==1);
    assert(c.pipeline_cache.lookups==1 && c.pipeline==&populated);

    Rasterizer missing;
    missing.pipeline_cache.current=nullptr;
    missing.Test();
    assert(missing.guest_descriptor_queue.checks==0);

    Configuration z;
    z.Apply();
    assert(z.guest_descriptor_queue.empties==1);
    assert(z.guest_descriptor_queue.acquires==0 && z.scheduler.waits==0);
    z.num_descriptor_entries=6;
    z.Apply();
    assert(z.guest_descriptor_queue.acquires==1 && z.scheduler.waits==0);
}
"""
with tempfile.TemporaryDirectory(prefix="encore-compute-empty-desc-") as folder:
    cpp = Path(folder) / "test.cpp"
    cpp.write_text(test)
    for opt in ("-O0", "-O2"):
        exe = Path(folder) / ("test" + opt)
        subprocess.run(["c++", "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", str(cpp), "-o", str(exe)], check=True, timeout=30)
        subprocess.run([str(exe)], check=True, timeout=10)
        print("COMPUTE_EMPTY_DESCRIPTOR_QUEUE_PASS", opt)
