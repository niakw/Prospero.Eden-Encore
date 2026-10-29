#!/usr/bin/env python3
"""F07: replay selected native Scheduler graphics state after DrawTexture blit.

The raw VkImage BlitColor overload records a graphics pipeline on the command
buffer without informing the scheduler, unlike BlitImpl. Verify that native
DrawTexture invalidates the cached guest graphics state afterward. HOST ONLY.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
raster = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
blit = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/blit_image.cpp").read_text()
sched = (root / "vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp").read_text()
gen = (root / "tools/prepare-vulkan-port.py").read_text()
cmake = (root / "headless/vulkan.cmake").read_text()


def fragment(source: str, begin: str, end: str) -> str:
    assert source.count(begin) == 1, ("begin", begin)
    rest = source.split(begin, 1)[1]
    assert end in rest, ("end", end)
    return begin + rest.split(end, 1)[0]


draw = fragment(raster, "void RasterizerVulkan::DrawTexture() {",
                "\nvoid RasterizerVulkan::Clear(")
raw = fragment(blit, "void BlitImageHelper::BlitColor(const Framebuffer* dst_framebuffer, VkImageView src_image_view,",
               "\nvoid BlitImageHelper::BlitImpl(")
ordinary = fragment(blit, "void BlitImageHelper::BlitImpl(",
                    "\nvoid BlitImageHelper::BlitColorMSAA(")
assert draw.count("blit_image.BlitColor(framebuffer, texture.RenderTarget()") == 1
assert draw.count("scheduler.InvalidateState();") == 1
assert draw.index("blit_image.BlitColor(framebuffer, texture.RenderTarget()") < draw.index("scheduler.InvalidateState();")
assert "gpu_memory->FlushCaching();" in draw.split("std::scoped_lock l{texture_cache.mutex};", 1)[0]
assert "cmdbuf.BindPipeline(VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);" in raw
assert "cmdbuf.BindDescriptorSets(VK_PIPELINE_BIND_POINT_GRAPHICS" in raw
assert "scheduler.InvalidateState();" not in raw
assert "scheduler.InvalidateState();" in ordinary
assert "PORT_BUILD_DIR" in cmake and "vulkan_rasterizer.cpp" in cmake
assert '"    scheduler.InvalidateState();\\n"' in gen
assert "F07 bypass cold guest graphics shader lookup in native raw DrawTexture" in gen
dmethod=fragment(raster, "void RasterizerVulkan::UpdateDynamicStates() {",
                 "\\nvoid RasterizerVulkan::HandleTransformFeedback(")
assert dmethod.count("if (device.IsExtVertexInputDynamicStateSupported()) {")==1
dynamic_branch=dmethod[dmethod.index("    if (device.IsExtVertexInputDynamicStateSupported()) {"):dmethod.rfind("\\n}")]
assert "if (prepared_pipeline && prepared_pipeline->HasDynamicVertexInput())" in dynamic_branch
assert dynamic_branch.count("pipeline_cache.CurrentGraphicsPipeline()")==1
assert dynamic_branch.index("#ifdef PS5_NATIVE") < dynamic_branch.index("#else")
assert "    UpdateDynamicStates();" in draw
assert draw.index("    std::scoped_lock l{texture_cache.mutex};") < draw.index("    UpdateDynamicStates();")


update = fragment(sched, "bool Scheduler::UpdateGraphicsPipeline(GraphicsPipeline* pipeline, bool optimized) {",
                  "\nbool Scheduler::UpdateRescaling(")
invalidate = fragment(sched, "void Scheduler::InvalidateState() {",
                      "\nvoid Scheduler::EndPendingOperations(")
assert "if (state.graphics_pipeline == pipeline)" in update
assert "state.graphics_pipeline = nullptr;" in invalidate
assert "state.graphics_pipeline_optimized = false;" in invalidate
assert "state.graphics_pipeline_optimized = optimized;" in update

# Compile the ACTUAL maintained Scheduler methods at O0/O2 with minimal host
# mocks for the Vulkan-independent state tracker and guest pipeline object.
cpp = r"""
#include <cassert>
struct GraphicsPipeline {
    bool UsesExtendedDynamicState() const { return false; }
};
struct StateTracker {
    int invalidations = 0;
    void InvalidateStateEnableFlag() {}
    void InvalidateCommandBufferState() { ++invalidations; }
};
class Scheduler {
public:
    struct State {
        GraphicsPipeline* graphics_pipeline = nullptr;
        bool graphics_pipeline_optimized = false;
        bool needs_state_enable_refresh = false;
        bool rescaling_defined = true;
        bool descriptor_buffer_bound = true;
    } state;
    StateTracker state_tracker;
    bool UpdateGraphicsPipeline(GraphicsPipeline* pipeline, bool optimized = false);
    void InvalidateState();
};
""" + update + "\n" + invalidate + r"""
int main() {
    Scheduler scheduler;
    GraphicsPipeline guest;
    assert(scheduler.UpdateGraphicsPipeline(&guest));
    assert(!scheduler.UpdateGraphicsPipeline(&guest));
    // A raw Vk pipeline blit changes the GPU command-buffer binding but leaves
    // Scheduler::state.graphics_pipeline referring to this guest pipeline.
    // Without invalidate, the following same guest shader skips rebinding.
    assert(!scheduler.UpdateGraphicsPipeline(&guest));
    // The same logical pipeline can publish its optimized handle mid-frame.
    // The new API must detect this even before the raw blit invalidation.
    assert(scheduler.UpdateGraphicsPipeline(&guest, true));
    assert(!scheduler.UpdateGraphicsPipeline(&guest, true));
    scheduler.InvalidateState();
    assert(scheduler.state.graphics_pipeline == nullptr);
    assert(!scheduler.state.graphics_pipeline_optimized);
    assert(!scheduler.state.rescaling_defined);
    assert(!scheduler.state.descriptor_buffer_bound);
    assert(scheduler.state_tracker.invalidations == 1);
    assert(scheduler.UpdateGraphicsPipeline(&guest, true));
    assert(!scheduler.UpdateGraphicsPipeline(&guest, true));
}
"""
with tempfile.TemporaryDirectory(prefix="fc27-f07-raw-blit-") as td:
    source = Path(td) / "test.cpp"
    source.write_text(cpp)
    for opt in ("-O0", "-O2"):
        executable = Path(td) / ("case" + opt[2:])
        subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                        opt, str(source), "-o", str(executable)],
                       check=True, capture_output=True, text=True)
        subprocess.run([str(executable)], check=True, capture_output=True, text=True)
# Prove the real native vertex-input branch never creates a cold guest shader
# on a raw blit (where prepared_pipeline is null), while it still programs
# dynamic vertex input for the next real guest draw. Desktop stays original.
dynamic_cpp = r"""
#include <cassert>
struct GraphicsPipeline {
    bool dynamic{};
    bool HasDynamicVertexInput() const { return dynamic; }
};
GraphicsPipeline* prepared_pipeline = nullptr;
struct Device {
    bool enabled = true;
    bool IsExtVertexInputDynamicStateSupported() const { return enabled; }
};
struct PipelineCache {
    GraphicsPipeline* selected = nullptr;
    unsigned lookups = 0;
    GraphicsPipeline* CurrentGraphicsPipeline() {
        ++lookups;
        return selected;
    }
};
struct FakeRasterizer {
    Device device;
    PipelineCache pipeline_cache;
    unsigned bindings = 0;
    void UpdateVertexInput(int&) { ++bindings; }
    void UpdateDynamicStates() {
        int regs = 0;
__DYNAMIC_BRANCH__
    }
};
int main() {
    GraphicsPipeline dynamic{true}, fixed{false};
    FakeRasterizer raw;
    raw.pipeline_cache.selected = &dynamic;
    raw.UpdateDynamicStates();
#ifdef PS5_NATIVE
    assert(raw.pipeline_cache.lookups == 0 && raw.bindings == 0);
#else
    assert(raw.pipeline_cache.lookups == 1 && raw.bindings == 1);
#endif
    FakeRasterizer guest;
    guest.pipeline_cache.selected = &fixed;
    prepared_pipeline = &dynamic;
    guest.UpdateDynamicStates();
    assert(guest.pipeline_cache.lookups == 0 && guest.bindings == 1);
    prepared_pipeline = &fixed;
    guest.UpdateDynamicStates();
    assert(guest.pipeline_cache.lookups == 0 && guest.bindings == 1);
    guest.device.enabled = false;
    prepared_pipeline = &dynamic;
    guest.UpdateDynamicStates();
    assert(guest.bindings == 1);
    prepared_pipeline = nullptr;
}
""".replace("__DYNAMIC_BRANCH__", dynamic_branch)
with tempfile.TemporaryDirectory(prefix="fc27-f07-raw-vertex-") as td:
    source = Path(td) / "dynamic.cpp"
    source.write_text(dynamic_cpp)
    for opt in ("-O0", "-O2"):
        for native in (False, True):
            executable = Path(td) / ("dyn" + opt[2:] + ("-ps5" if native else "-desktop"))
            args = ["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=undefined", "-fno-sanitize-recover=all", opt,
                    *(["-DPS5_NATIVE=1"] if native else []),
                    str(source), "-o", str(executable)]
            subprocess.run(args, check=True, capture_output=True, text=True)
            subprocess.run([str(executable)], check=True, capture_output=True, text=True)
print("FC27_F07_RAW_BLIT_PIPELINE_INVALIDATION_PASS source_extracted=3 raw_blit_avoids_guest_shader=1 desktop_original=1 O0=1 O2=1")

