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
assert "const bool optimized_at_record = optimized_ready.load(std::memory_order_acquire);" in graphics
assert "scheduler.UpdateGraphicsPipeline(this, optimized_at_record)" in graphics
assert "bind_pipeline, optimized_at_record, update_descriptors" in graphics
assert "optimized_ready.store(true, std::memory_order_release);" in graphics
# F07 recovery now snapshots the published handle before its null check.
# Rebinding and recovery share the same release/acquire publication contract.
assert "const bool use_optimized = optimized_ready.load(std::memory_order_acquire);" in graphics
assert "if (!pipeline && !use_optimized)" in graphics
assert "use_optimized ? *optimized_pipeline : *pipeline" in graphics
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


# F07: the Vulkan worker already chooses a published optimized handle when
# the first-use driver handle is null. Its subsequent Draw/DrawIndirect worker
# callbacks MUST use exactly the same validity rule, otherwise recovered HUD
# draw calls are discarded despite a successful optimized rebuild.
graphics_header = (vulkan / "include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
admission_begin = "    [[nodiscard]] bool CanExecuteDraw() const noexcept {"
admission_end = "\n\n    template <typename Spec>"
assert graphics_header.count(admission_begin) == graphics_header.count(admission_end) == 1
admission = graphics_header[
    graphics_header.index(admission_begin):graphics_header.index(
        admission_end, graphics_header.index(admission_begin))]
assert "if (!is_built.load(std::memory_order::acquire)) return false;" in admission
assert "optimized_ready.load(std::memory_order_acquire)" in admission
assert "return static_cast<bool>(pipeline) ||" in admission
assert "#else\n        return static_cast<bool>(pipeline);\n#endif" in admission
assert "return static_cast<bool>(pipeline) ||" in generator
assert "if (!is_built.load(std::memory_order::acquire)) return false;" in generator
assert "optimized_ready.load(std::memory_order_acquire);" in generator
assert graphics.count("if (!pipeline && !use_optimized)") == 1
assert graphics.count("optimized_ready.store(true, std::memory_order_release);") == 1
raster = (vulkan / "vulkan_rasterizer.cpp").read_text()
assert raster.count("!pipeline || !pipeline->CanExecuteRecordedDraw()") == 4
assert "CanExecuteRecordedDraw() const noexcept" in admission
assert "worker_draw_bind_valid" in admission
assert "CanExecuteRecordedDraw() const noexcept" in generator
assert "F07 native worker bound-pipeline validity publish" in generator
assert "worker_draw_bind_valid = false;" in graphics
assert "worker_draw_bind_valid = true;" in graphics
assert "if (IsBuilt() && !pipeline && !optimized_ready.load(std::memory_order_acquire))" in graphics

recovery_cpp = r"""
#include <atomic>
#include <cassert>
#include <cstdio>
#include <thread>
struct FakeVkPipeline {
    bool valid{};
    explicit operator bool() const noexcept { return valid; }
};
struct GraphicsPipeline {
    FakeVkPipeline pipeline{};
    std::atomic_bool is_built{false};
    std::atomic_bool optimized_ready{false};
#ifdef PS5_NATIVE
    bool worker_draw_bind_valid{};
#endif
    unsigned optimized_driver_handle{};
__ACTUAL_ADMISSION__
};
int main() {
    GraphicsPipeline p;
    assert(!p.CanExecuteDraw());
    p.pipeline.valid = true;
    assert(!p.CanExecuteDraw());  // build not yet published
    p.is_built.store(true, std::memory_order_release);
    assert(p.CanExecuteDraw());   // primary pipeline works on both targets
    p.pipeline.valid = false;
    assert(!p.CanExecuteDraw());  // no valid pipeline at all

    // A background compiler can publish the replacement after the original
    // fast-first pipeline failed. The reader must acquire its handle safely.
    std::thread builder([&] {
        p.optimized_driver_handle = 0xBEEF;
        p.optimized_ready.store(true, std::memory_order_release);
    });
    // Join is deterministic and synchronizes the mock driver's published
    // handle. The separate FIFO test below covers the earlier/later
    // ConfigureDraw race without a timing-dependent busy-spin.
    builder.join();
#ifdef PS5_NATIVE
    assert(p.optimized_driver_handle == 0xBEEF && p.CanExecuteDraw());
#else
    assert(!p.CanExecuteDraw());  // desktop behavior remains unchanged
#endif
    p.is_built.store(false, std::memory_order_release);
    assert(!p.CanExecuteDraw());  // worker never submits a build in progress
    std::puts("F07_OPTIMIZED_RECOVERY_DRAW_PASS");
}
""".replace("__ACTUAL_ADMISSION__", admission)
with tempfile.TemporaryDirectory(prefix="eden-f07-recovery-draw-") as directory:
    path = Path(directory) / "recovery.cpp"
    path.write_text(recovery_cpp)
    for define in ([], ["-DPS5_NATIVE=1"]):
        for opt in ("-O0", "-O2"):
            binary = Path(directory) / ("recovery" + opt[1:] +
                                        ("-native" if define else "-desktop"))
            built = subprocess.run(
                [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                 "-pthread", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 *define, str(path), "-o", str(binary)],
                capture_output=True, text=True, timeout=40)
            assert built.returncode == 0, (define, opt, built.stderr[-5000:])
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
            assert ran.returncode == 0, (define, opt, ran.stdout, ran.stderr[-5000:])
            assert "F07_OPTIMIZED_RECOVERY_DRAW_PASS" in ran.stdout
            print("F07_OPTIMIZED_RECOVERY_DRAW_PASS", "native" if define else "desktop", opt)


# Source-extract the exact ordered Vulkan-worker decision. A replacement
# published between the ConfigureDraw and Draw callbacks MUST NOT make a
# previously skipped binding appear valid. Only the NEXT ConfigureDraw may
# rebind it. This is a real FIFO regression, not a conceptual validity model.
worker_start = "        const bool use_optimized = optimized_ready.load(std::memory_order_acquire);"
worker_end = "        cmdbuf.PushConstants("
worker_pos = graphics.index(worker_start, graphics.index("scheduler.Record([this, descriptor_data"))
worker_segment = graphics[worker_pos:graphics.index(worker_end, worker_pos)]
assert worker_segment.count("worker_draw_bind_valid = false;") == 1
assert worker_segment.count("worker_draw_bind_valid = true;") == 1
assert worker_segment.index("worker_draw_bind_valid = false;") < worker_segment.index(
    "if (!pipeline && !use_optimized)"
)
assert worker_segment.index("worker_draw_bind_valid = true;") > worker_segment.index(
    "cmdbuf.BindPipeline("
)

fifo_cpp = r"""
#include <atomic>
#include <cassert>
#include <cstdio>
struct FakeVkPipeline {
    bool valid{};
    int value{};
    explicit operator bool() const noexcept { return valid; }
    int operator*() const { assert(valid); return value; }
};
constexpr int VK_PIPELINE_BIND_POINT_GRAPHICS = 0;
struct FakeCmd {
    int bound{};
    unsigned binds{};
    void BindPipeline(int, int value) { bound = value; ++binds; }
};
namespace Eden::Performance {
enum class GraphicsDrawDrop { WorkerPipelineFailed };
inline unsigned failed{};
inline void RecordGraphicsDrawDrop(GraphicsDrawDrop) { ++failed; }
}
struct GraphicsPipeline {
    FakeVkPipeline pipeline{}, optimized_pipeline{};
    std::atomic_bool is_built{true}, optimized_ready{false};
#ifdef PS5_NATIVE
    bool worker_draw_bind_valid{};
#endif
__ACTUAL_ADMISSION__
    void BindRecorded(FakeCmd& cmdbuf, bool bind_pipeline,
                      bool optimized_at_record) {
__ACTUAL_WORKER_BODY__
    }
};
int main() {
    GraphicsPipeline p;
    FakeCmd cmdbuf;
    assert(!p.CanExecuteRecordedDraw());
    p.BindRecorded(cmdbuf, true, false);
    assert(cmdbuf.binds == 0);
    assert(!p.CanExecuteRecordedDraw());
    // Later driver success is NOT a retroactive bind for the previous Draw.
    p.optimized_pipeline.valid = true;
    p.optimized_pipeline.value = 0xBEEF;
    p.optimized_ready.store(true, std::memory_order_release);
#ifdef PS5_NATIVE
    assert(p.CanExecuteDraw() && !p.CanExecuteRecordedDraw());
#else
    assert(!p.CanExecuteDraw() && !p.CanExecuteRecordedDraw());
#endif
    // Next FIFO ConfigureDraw detects the newly published variant and binds it.
    p.BindRecorded(cmdbuf, false, false);
    assert(cmdbuf.binds == 1 && cmdbuf.bound == 0xBEEF);
#ifdef PS5_NATIVE
    assert(p.CanExecuteRecordedDraw());
#else
    assert(!p.CanExecuteRecordedDraw());
#endif
    // A valid initial Vulkan build is also a legal selection.
    p.optimized_ready.store(false, std::memory_order_release);
    p.pipeline.valid = true;
    p.pipeline.value = 0x1234;
    p.BindRecorded(cmdbuf, true, false);
    assert(cmdbuf.binds == 2 && cmdbuf.bound == 0x1234);
    assert(p.CanExecuteRecordedDraw());
    // Recheck failure on every ConfigureDraw: an earlier successful bind does
    // not entitle an invalid later command to reuse that old VkPipeline.
    p.pipeline.valid = false;
    p.BindRecorded(cmdbuf, true, false);
#ifdef PS5_NATIVE
    assert(!p.CanExecuteRecordedDraw());
#else
    assert(!p.CanExecuteRecordedDraw());
#endif
    assert(Eden::Performance::failed == 2);
    std::puts("F07_RECOVERED_WORKER_FIFO_BIND_PASS");
}
""".replace("__ACTUAL_ADMISSION__", admission).replace(
    "__ACTUAL_WORKER_BODY__", worker_segment)
with tempfile.TemporaryDirectory(prefix="eden-f07-recovered-worker-") as directory:
    path = Path(directory) / "recovered.cpp"
    path.write_text(fifo_cpp)
    for define in ([], ["-DPS5_NATIVE=1"]):
        for opt in ("-O0", "-O2"):
            binary = Path(directory) / ("fifo" + opt[1:] +
                                        ("-native" if define else "-desktop"))
            built = subprocess.run(
                [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 *define, str(path), "-o", str(binary)],
                capture_output=True, text=True, timeout=40)
            assert built.returncode == 0, (define, opt, built.stderr[-5000:])
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
            assert ran.returncode == 0, (define, opt, ran.stdout, ran.stderr[-5000:])
            assert "F07_RECOVERED_WORKER_FIFO_BIND_PASS" in ran.stdout
            print("F07_RECOVERED_WORKER_FIFO_BIND_PASS", "native" if define else "desktop", opt)
