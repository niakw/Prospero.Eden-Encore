#!/usr/bin/env python3
"""F07 DEV-only Vulkan optimized-pipeline promotion; selected native O0/O2.

Scheduler maps GraphicsPipeline* identity, but fast-first background optimization
replaces its *VkPipeline* handle without changing that identity. Verify the native
ConfigureDraw rebind decision retains the fast path and forces one promotion bind.
Not a measured production FPS improvement; no PS5 GPU execution in host test.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/"vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
header = (root/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
generator = (root/"tools/prepare-vulkan-port.py").read_text()
oracle = (root/"tools/check-vendored-vulkan-fork.py").read_text()
start = "    const bool scheduler_pipeline_changed{scheduler.UpdateGraphicsPipeline(this)};"
end = "    const bool bind_descriptor_buffer{"
assert source.count(start) == 1 and end in source.split(start, 1)[1]
fragment = start + source.split(start, 1)[1].split(end, 1)[0]
assert "optimized_ready.load(std::memory_order_acquire)" in fragment
assert "optimized_promotion_bound = true;" in fragment
assert "scheduler_pipeline_changed || optimized_promotion" in fragment
assert header.count("bool optimized_promotion_bound{};") == 1
assert "bool optimized_promotion_bound{};" in generator
assert "new_bind = '''" in oracle
assert "new_promotion = " in oracle
assert "optimized_ready.load(std::memory_order_acquire) ? *optimized_pipeline : *pipeline" in source

cpp = r"""
#include <atomic>
#include <cassert>
class GraphicsPipeline;
struct Scheduler {
    GraphicsPipeline* current{};
    bool UpdateGraphicsPipeline(GraphicsPipeline* pipeline) {
        const bool changed = current != pipeline;
        current = pipeline;
        return changed;
    }
    void Reset() { current = nullptr; }
};
class GraphicsPipeline {
public:
    std::atomic_bool optimized_ready{false};
    bool optimized_promotion_bound{};
    bool Bind(Scheduler& scheduler) {
""" + fragment + r"""
        return bind_pipeline;
    }
};
int main() {
    Scheduler scheduler;
    GraphicsPipeline guest, other;
    assert(guest.Bind(scheduler));  // first nonoptimized guest draw
    assert(!guest.Bind(scheduler)); // identical pipeline, keep fast reuse
    assert(!guest.optimized_promotion_bound);
    guest.optimized_ready.store(true, std::memory_order_release);
    assert(guest.Bind(scheduler));  // same guest pointer, NEW VkPipeline
    assert(guest.optimized_promotion_bound);
    assert(!guest.Bind(scheduler)); // no redundant Vulkan bind per draw
    assert(other.Bind(scheduler));  // guest shader switched
    assert(guest.Bind(scheduler));  // normal shader-switch bind still works
    assert(!guest.Bind(scheduler));
    scheduler.Reset();              // new command buffer invalidates old bind
    assert(guest.Bind(scheduler));
    GraphicsPipeline already_optimized;
    already_optimized.optimized_ready.store(true, std::memory_order_release);
    assert(already_optimized.Bind(scheduler)); // precompiled shader
    assert(!already_optimized.Bind(scheduler));
    GraphicsPipeline unoptimized;
    assert(unoptimized.Bind(scheduler));
    assert(!unoptimized.Bind(scheduler));
}
"""
with tempfile.TemporaryDirectory(prefix="fc27-f07-pipeline-promotion-") as tmp:
    target = Path(tmp) / "test.cpp"
    target.write_text(cpp)
    for opt in ("-O0", "-O2"):
        exe = Path(tmp) / ("promotion"+opt[2:])
        subprocess.run(["c++", "-std=c++20", "-DPS5_NATIVE=1", "-Wall", "-Wextra", "-Werror",
                        opt, str(target), "-o", str(exe)], check=True, capture_output=True, text=True)
        subprocess.run([str(exe)], check=True, capture_output=True, text=True)
print("FC27_F07_OPTIMIZED_PROMOTION_HOST_PASS selected_gpu_owner=1 O0=1 O2=1 first_use=1 exactly_once=1")
