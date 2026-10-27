#!/usr/bin/env python3
"""F07: bind a newly optimized Vulkan variant even with an unchanged owner."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
vulkan = root / "vendor/encore-active/eden-vulkan"
sched = (vulkan / "vulkan_scheduler.cpp").read_text()
header = (vulkan / "include/video_core/renderer_vulkan/vk_scheduler.h").read_text()
graphics = (vulkan / "vk_graphics_pipeline_cost.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
begin = "bool Scheduler::UpdateGraphicsPipeline(GraphicsPipeline* pipeline, bool optimized) {"
end = "\n\nbool Scheduler::UpdateRescaling("
assert sched.count(begin) == 1
method = sched[sched.index(begin):sched.index(end, sched.index(begin))]
a = sched.index("void Scheduler::InvalidateState() {")
b = sched.index("\n\nvoid Scheduler::EndPendingOperations(", a)
invalidate = sched[a:b]
assert method.count("state.graphics_pipeline_optimized = optimized;") == 2
assert "const bool variant_changed = state.graphics_pipeline_optimized != optimized;" in method
assert "state.graphics_pipeline_optimized = false;" in invalidate
assert "bool graphics_pipeline_optimized = false;" in header
assert "UpdateGraphicsPipeline(GraphicsPipeline* pipeline, bool optimized = false)" in header
assert "this, optimized_ready.load(std::memory_order_acquire))" in graphics
assert "optimized_ready.store(true, std::memory_order_release);" in graphics
assert "optimized_ready.load(std::memory_order_acquire) ? *optimized_pipeline : *pipeline" in graphics
assert "F07 scheduler variant change rebind" in generator
assert "F07 graphics optimize publication handoff" in generator

code = r"""
#include <cassert>
struct GraphicsPipeline {
    bool extended{};
    bool UsesExtendedDynamicState() const { return extended; }
};
struct Tracker {
    int enables{}, invalidations{};
    void InvalidateStateEnableFlag() { ++enables; }
    void InvalidateCommandBufferState() { ++invalidations; }
};
struct Scheduler {
    struct State {
        GraphicsPipeline* graphics_pipeline{};
        bool graphics_pipeline_optimized{};
        bool needs_state_enable_refresh{};
        bool rescaling_defined{};
        bool descriptor_buffer_bound{};
    } state;
    Tracker state_tracker;
    bool UpdateGraphicsPipeline(GraphicsPipeline*, bool);
    void InvalidateState();
};
""" + method + "\n" + invalidate + r"""
int main() {
    Scheduler scheduler;
    GraphicsPipeline initial{false}, other{true};
    assert(scheduler.UpdateGraphicsPipeline(&initial, false));
    assert(!scheduler.UpdateGraphicsPipeline(&initial, false));
    assert(scheduler.UpdateGraphicsPipeline(&initial, true));
    assert(!scheduler.UpdateGraphicsPipeline(&initial, true));
    assert(scheduler.state_tracker.invalidations == 0);
    assert(scheduler.UpdateGraphicsPipeline(&other, false));
    assert(scheduler.state_tracker.enables == 1);
    assert(!scheduler.UpdateGraphicsPipeline(&other, false));
    assert(scheduler.UpdateGraphicsPipeline(&other, true));
    assert(!scheduler.UpdateGraphicsPipeline(&other, true));
    scheduler.InvalidateState();
    assert(!scheduler.state.graphics_pipeline_optimized);
    assert(scheduler.state_tracker.invalidations == 1);
    assert(scheduler.UpdateGraphicsPipeline(&other, true));
    assert(!scheduler.UpdateGraphicsPipeline(&other, true));
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++ compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-variant-") as directory:
    source = Path(directory) / "test.cpp"
    source.write_text(code)
    for opt in ("-O0", "-O2"):
        binary = Path(directory) / ("test" + opt[1:])
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(source), "-o", str(binary)], check=True, timeout=40)
        subprocess.run([str(binary)], check=True, timeout=20)
print("F07_PIPELINE_VARIANT_REBIND_PASS same_owner=1 transition=1 invalidation=1 O0=1 O2=1")
