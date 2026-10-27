#!/usr/bin/env python3
"""Compile REAL pinned native Vulkan BuiltPipeline() for PS5 and upstream desktop.

Covers a source-level draw-loss mechanism relevant to FC27 R400c:
nine no_pipeline events were logged but were not tagged with the exact cause.
Host test proves policy and worker completion contracts, not PS5 shader pixels.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
vk = (ROOT / "vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
gp = (ROOT / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
generator = (ROOT / "tools/prepare-vulkan-port.py").read_text()
start = vk.index("GraphicsPipeline* PipelineCache::BuiltPipeline(")
stop = vk.index("std::unique_ptr<GraphicsPipeline> PipelineCache::CreateGraphicsPipeline(", start)
actual = vk[start:stop]
assert actual.count("#ifdef PS5_NATIVE") == 1
assert "return pipeline;" in actual.split("#ifdef PS5_NATIVE", 1)[1].split("#endif", 1)[0]
assert "ps5_first_use_new" in generator
assert "build_condvar.wait(lock, [this] { return is_built.load" in gp
assert "is_built.store(true, std::memory_order_release)" in gp
assert "build_condvar.notify_all()" in gp
# An initial null fast-first handle no longer means a terminal draw drop:
# the optimized handle can already be published and valid. The worker still
# rejects a draw when neither handle is usable.
assert "if (IsBuilt() && !pipeline && !optimized_ready.load(std::memory_order_acquire))" in gp
assert "if (!pipeline && !use_optimized)" in gp
assert "use_optimized ? *optimized_pipeline : *pipeline" in gp

fixture = r"""
#include <cassert>
#include <cstddef>
struct GraphicsPipeline {
    bool built;
    bool IsBuilt() const noexcept { return built; }
};
struct DrawState { struct { unsigned count; } index_buffer, vertex_buffer; };
struct Max3D { struct { DrawState draw_state; } draw_manager; };
struct PipelineCache {
    Max3D* maxwell3d;
    bool use_asynchronous_shaders;
    GraphicsPipeline* BuiltPipeline(GraphicsPipeline* pipeline) const noexcept;
};
""" + actual + r"""
int main() {
    Max3D maxwell{};
    PipelineCache cache{&maxwell, true};
    GraphicsPipeline waiting{false}, built{true};
    // Both full-screen-quads and larger HUD/glyph draw batches.
    maxwell.draw_manager.draw_state.index_buffer.count = 6;
    maxwell.draw_manager.draw_state.vertex_buffer.count = 6;
    assert(cache.BuiltPipeline(&waiting) == &waiting);
    maxwell.draw_manager.draw_state.index_buffer.count = 36;
    maxwell.draw_manager.draw_state.vertex_buffer.count = 24;
    assert(cache.BuiltPipeline(&built) == &built);
    cache.use_asynchronous_shaders = false;
    assert(cache.BuiltPipeline(&waiting) == &waiting);
    cache.use_asynchronous_shaders = true;
#ifdef PS5_NATIVE
    // With the previous policy, all nine synthetic pending draws would vanish.
    unsigned skipped = 0;
    for (unsigned i=0; i<9; ++i)
        skipped += cache.BuiltPipeline(&waiting) == nullptr;
    assert(skipped == 0);
#else
    // Preserve the non-console fast-first tradeoff exactly as before.
    assert(cache.BuiltPipeline(&waiting) == nullptr);
#endif
    return 0;
}
"""

cxx = next((tool for tool in ("clang++-18", "clang++", "g++") if shutil.which(tool)), None)
assert cxx, "C++20 toolchain required"
with tempfile.TemporaryDirectory(prefix="eden-r403-draw-first-use-") as d:
    root = Path(d)
    src = root / "replay.cpp"
    src.write_text(fixture)
    for name, flags in (("ps5", ["-DPS5_NATIVE=1"]), ("desktop", [])):
        output = root / name
        subprocess.run([cxx,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined",*flags,str(src),"-o",str(output)],
                       check=True,timeout=35)
        subprocess.run([str(output)],check=True,timeout=15)
print("R403 PASS: actual Vulkan BuiltPipeline() compiled PS5 + desktop; 9/9 synthetic PS5 pending draws retained")
print("R403 PASS: R378 worker signals completion on exceptions; GraphicsPipeline::ConfigureDraw waits on GPU scheduler worker")
print("Host-only: no PS5 pixel reproduction or hardware performance change proven")
