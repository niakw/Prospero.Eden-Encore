#!/usr/bin/env python3
"""Source-extracted graphics callback: retry with a published optimized handle.

Tests C++20 Vulkan-handle decisions at -O0/-O2, no real GPU driver.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
gen = (root / "tools/prepare-vulkan-port.py").read_text()
begin = "        if (bind_pipeline) {\n            // An initial fast-first Vulkan creation"
end = "\n        cmdbuf.PushConstants"
assert src.count(begin) == 1
callback = src[src.index(begin):src.index(end, src.index(begin))]
assert callback.count("optimized_ready.load(std::memory_order_acquire)") == 1
assert callback.index("const bool use_optimized") < callback.index("if (!pipeline && !use_optimized)")
assert callback.index("if (!pipeline && !use_optimized)") < callback.index("cmdbuf.BindPipeline")
assert "use_optimized ? *optimized_pipeline : *pipeline" in callback
assert "F07 recovered optimized draw handle after initial fast-first failure" in gen
assert gen.count("apply_reviewed_delta(\"vk_graphics_pipeline_cost.cpp\",") >= 1

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
    void Run(CommandBuffer& cmdbuf, bool bind_pipeline) {
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
    test.Run(cmd, true);
    assert(cmd.bound == 11);
    test.optimized_pipeline = 22;
    test.optimized_ready.store(true, std::memory_order_release);
    cmd.bound = -1;
    test.Run(cmd, true);
    assert(cmd.bound == 22);
    // The critical recovery: initial driver handle failed; optimize succeeds.
    test.pipeline.reset();
    cmd.bound = -1;
    test.Run(cmd, true);
    assert(cmd.bound == 22 && Eden::Performance::failures == 0);
    test.optimized_ready.store(false, std::memory_order_release);
    cmd.bound = -1;
    test.Run(cmd, true);
    assert(cmd.bound == -1 && Eden::Performance::failures == 1);
    test.optimized_pipeline.reset();
    test.pipeline = 33;
    cmd.bound = -1;
    test.Run(cmd, true);
    assert(cmd.bound == 33 && Eden::Performance::failures == 1);
    // No bind request remains a no-op, not a stale extra submission.
    cmd.bound = -1;
    test.Run(cmd, false);
    assert(cmd.bound == -1 && Eden::Performance::failures == 1);
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
print("F07_OPTIMIZED_DRAW_RECOVERY_PASS baseline=1 optimized=1 null_baseline_recovered=1 both_missing_dropped=1 O0=1 O2=1")
