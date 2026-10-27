#!/usr/bin/env python3
"""F07: prove selected worker draw validity and late optimized publication.

Compiles source-extracted callback and validates selected source/generator
parity; no GPU timing or console presentation claims.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
gen = (root / "tools/prepare-vulkan-port.py").read_text()
begin = "        // The worker must verify validity on EVERY draw:"
end = "\n        cmdbuf.PushConstants"
assert src.count(begin) == 1
callback = src[src.index(begin):src.index(end, src.index(begin))]
assert callback.count("optimized_ready.load(std::memory_order_acquire)") == 1
assert callback.index("if (!pipeline && !use_optimized)") < callback.index("if (bind_pipeline ||")
assert "use_optimized != optimized_at_record" in callback
assert "use_optimized ? *optimized_pipeline : *pipeline" in callback
assert src.count("if (IsBuilt() && !pipeline && !optimized_ready.load(std::memory_order_acquire))") == 1
assert "bind_pipeline, optimized_at_record, update_descriptors" in src
assert "scheduler.UpdateGraphicsPipeline(this, optimized_at_record)" in src
for anchor in (
    "F07 recover optimized built pipeline",
    "F07 snapshot optimized variant",
    "F07 capture pipeline variant snapshot",
    "F07 validate every worker draw and late publish",
):
    assert anchor in gen, anchor

code = r"""
#include <atomic>
#include <cassert>
#include <optional>
using Pipeline = std::optional<int>;
constexpr int VK_PIPELINE_BIND_POINT_GRAPHICS = 1;
namespace Eden { namespace Performance {
enum class GraphicsDrawDrop { WorkerPipelineFailed };
inline int failures{};
void RecordGraphicsDrawDrop(GraphicsDrawDrop) { ++failures; }
}}
struct CommandBuffer {
    int bound{-1};
    void BindPipeline(int, int value) { bound = value; }
};
struct Mock {
    Pipeline pipeline{}, optimized_pipeline{};
    std::atomic_bool optimized_ready{false};
    void Run(CommandBuffer& cmdbuf, bool bind_pipeline, bool optimized_at_record) {
        auto work = [&]() {
""" + callback + r"""
        };
        work();
    }
};
int main() {
    Mock test;
    CommandBuffer cmd;
    test.pipeline = 11;
    test.Run(cmd, true, false);
    assert(cmd.bound == 11);
    test.optimized_pipeline = 22;
    test.optimized_ready.store(true, std::memory_order_release);
    cmd.bound = -1;
    test.Run(cmd, true, true);
    assert(cmd.bound == 22);
    // Initial driver handle may be null yet optimization succeeded.
    test.pipeline.reset();
    cmd.bound = -1;
    test.Run(cmd, true, true);
    assert(cmd.bound == 22 && Eden::Performance::failures == 0);
    // Publication after the GPU owner recorded no binding change.
    cmd.bound = -1;
    test.Run(cmd, false, false);
    assert(cmd.bound == 22);
    // Already selected optimized handle: no redundant bind.
    cmd.bound = -1;
    test.Run(cmd, false, true);
    assert(cmd.bound == -1);
    test.optimized_ready.store(false, std::memory_order_release);
    cmd.bound = -1;
    test.Run(cmd, true, false);
    assert(cmd.bound == -1 && Eden::Performance::failures == 1);
    // Crucial: a failed pipeline is still selected by the scheduler.
    // Never draw using a stale handle when bind_pipeline is false.
    cmd.bound = -1;
    test.Run(cmd, false, false);
    assert(cmd.bound == -1 && Eden::Performance::failures == 2);
    test.optimized_pipeline.reset();
    test.pipeline = 33;
    cmd.bound = -1;
    test.Run(cmd, true, false);
    assert(cmd.bound == 33 && Eden::Performance::failures == 2);
    // No transition and a valid baseline handle: no extra bind.
    cmd.bound = -1;
    test.Run(cmd, false, false);
    assert(cmd.bound == -1 && Eden::Performance::failures == 2);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-f07-opt-recovery-") as folder:
    path = Path(folder) / "recovery.cpp"
    path.write_text(code)
    for mode in ("-O0", "-O2"):
        exe = Path(folder) / ("test" + mode[1:])
        subprocess.run([compiler, "-std=c++20", mode, "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(path), "-o", str(exe)], check=True, timeout=40)
        subprocess.run([str(exe)], check=True, timeout=20)
print("F07_OPTIMIZED_DRAW_RECOVERY_PASS baseline=1 optimized=1 recovered=1 late_ready=1 stale_handle_rejected=1 O0=1 O2=1")
