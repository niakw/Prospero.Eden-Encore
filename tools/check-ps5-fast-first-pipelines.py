#!/usr/bin/env python3
"""R313: verify first-use pipelines are fast, cached ones unchanged, worker lifetime safe."""
from pathlib import Path
import ast
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
generator = (root / "tools/prepare-vulkan-port.py").read_text()
dev = (root / "headless/dev_vulkan.h").read_text()
main = (root / "headless/main.cpp").read_text()

nodes = ast.parse(generator).body
workers = [ast.literal_eval(stmt.value) for stmt in nodes
           if isinstance(stmt, ast.Assign)
           and any(isinstance(t, ast.Name) and t.id == "optimize_worker"
                   for t in stmt.targets)]
assert len(workers) == 1
worker = workers[0]

for expected in (
    "static Common::ThreadWorker worker(1,",
    "if (!state) return;",
    "state->cancelled = true;",
    "state->done.wait(lock, [&] { return !state->running; });",
    "if (state->cancelled) return;",
    "optimized_ready.store(true, std::memory_order_release);",
    "state->running = false;",
    "state->done.notify_all();",
    "CompletionGuard",
    "if (optimized_pipeline)",
    "catch (const std::exception& exception)",
    "catch (...)",
):
    assert expected in worker, expected
assert "VulkanTimer(24)" not in worker
assert worker.index("build_condvar.wait(build_lock") < worker.index("const auto state = optimize_state;")
assert "is_built.load(std::memory_order_acquire)" in worker
assert worker in (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()  # performance.h uses std::array<Totals,24>, 0..23
assert "std::make_shared<OptimizeState>()" in worker
assert worker.index("state->running = true;") < worker.index("OptimizeWorker().QueueWork")
assert worker.count("state->running = true;") == 1
assert "state->running = false;" in worker
assert "worker_thread != nullptr" in generator  # disk preload worker pointer null
assert "VK_PIPELINE_CREATE_DISABLE_OPTIMIZATION_BIT" in generator
assert "optimized_ready.load(std::memory_order_acquire)" in generator
assert "target ? *target : pipeline" in generator
assert "void QueueOptimizedPipeline(VkRenderPass render_pass);" in generator
assert "std::shared_ptr<OptimizeState> optimize_state;" in generator
assert "fast_first_pipelines = true;" in dev and "fast_first_pipelines = false;" in dev
assert "fast_pipelines=off" in main and "fast_pipelines=on" in main
assert "EDEN_DEV_PROFILE" in dev
# The F07 post-adaptation transition memo legitimately references this path
# again. Uniqueness must cover the R313 source adaptation, not every mention.
assert generator.count("adapt('src/video_core/renderer_vulkan/vk_graphics_pipeline.h'") == 1
assert "transition_header = output / 'include/video_core/renderer_vulkan/vk_graphics_pipeline.h'" in generator

# Compile the precise native C++ optimization worker/dtor/queue implementation,
# not a Python approximation. A queued job after object destruction must see
# cancelled=true BEFORE any access to 'this'.
code = r"""
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
#include <cassert>
#include <stdexcept>
#define LOG_WARNING(...) ((void)0)
using VkRenderPass = int;
using VkPipelineCreateFlags = int;
namespace vk { using Pipeline = int; }
namespace Common {
class ThreadWorker {
public:
    ThreadWorker(int count, const char*) { assert(count == 1); }
    inline static std::atomic_bool reject_next{false};
    template<class F> void QueueWork(F func) {
        if (reject_next.exchange(false)) throw std::runtime_error("queue rejected");
        jobs.emplace_back([func = std::move(func)]() mutable {
            std::this_thread::sleep_for(std::chrono::milliseconds(4));
            func();
        });
    }
    ~ThreadWorker() { for (auto& job : jobs) job.join(); }
    std::vector<std::thread> jobs;
};
}
class GraphicsPipeline {
public:
    struct OptimizeState {
        std::mutex mutex;
        std::condition_variable done;
        bool cancelled{false};
        bool running{false};
    };
    std::shared_ptr<OptimizeState> optimize_state;
    // Existing optimization tests construct a finished first-use baseline.
    // A separate scenario below forces the constructor's worker to stay queued.
    std::atomic_bool is_built{true};
    std::mutex build_mutex;
    std::condition_variable build_condvar;
    vk::Pipeline optimized_pipeline{};
    std::atomic_bool optimized_ready{false};
    ~GraphicsPipeline();
    void QueueOptimizedPipeline(VkRenderPass);
    void MakePipeline(VkRenderPass, VkPipelineCreateFlags, vk::Pipeline*);
};
""" + worker + r"""
    // The body above is the actual generated native TU method signature.
    // This stub models Vulkan CreateGraphicsPipeline on a worker and the
    // release/acquire transfer to the main GPU thread.
    if (render_pass == -1) throw std::runtime_error("mock driver exception");
    if (target) *target = render_pass == 0 ? 0 : render_pass + extra_flags + 44;
}
int main() {
    for (int i = 0; i < 100; ++i) {
        GraphicsPipeline p;
        p.QueueOptimizedPipeline(11);
        // The queued job is already counted before it can start.
        assert(p.optimize_state->running);
        if (i % 2 == 0) {
            // Destroy before a queued worker starts. Must cancel safely.
            continue;
        }
        for (int spin = 0; spin < 1000000 &&
             !p.optimized_ready.load(std::memory_order_acquire); ++spin)
            std::this_thread::yield();
        assert(p.optimized_ready.load(std::memory_order_acquire));
        assert(p.optimized_pipeline == 55);
    }
    for (int pass : {0, -1}) {
        GraphicsPipeline p;
        p.QueueOptimizedPipeline(pass);
        const auto state = p.optimize_state;
        std::unique_lock lock{state->mutex};
        state->done.wait(lock, [&] { return !state->running; });
        assert(!p.optimized_ready.load(std::memory_order_acquire));
    }
    // Destroy a pipeline while its FIRST-use worker is still queued, before
    // the optimizer can publish optimize_state. Deletion must block until
    // initial pipeline publication; otherwise the worker retains a dead this.
    {
        auto* p = new GraphicsPipeline;
        p->is_built.store(false, std::memory_order_release);
        std::atomic_bool allow_build{false};
        std::atomic_bool destroy_started{false};
        std::atomic_bool destroyed{false};
        std::thread build([p, &allow_build] {
            while (!allow_build.load(std::memory_order_acquire))
                std::this_thread::yield();
            {
                std::scoped_lock lock{p->build_mutex};
                p->is_built.store(true, std::memory_order_release);
            }
            p->build_condvar.notify_all();
        });
        std::thread teardown([p, &destroy_started, &destroyed] {
            destroy_started.store(true, std::memory_order_release);
            delete p;
            destroyed.store(true, std::memory_order_release);
        });
        while (!destroy_started.load(std::memory_order_acquire))
            std::this_thread::yield();
        std::this_thread::sleep_for(std::chrono::milliseconds(8));
        assert(!destroyed.load(std::memory_order_acquire));
        allow_build.store(true, std::memory_order_release);
        build.join();
        teardown.join();
        assert(destroyed.load(std::memory_order_acquire));
    }
    {
        GraphicsPipeline p;
        Common::ThreadWorker::reject_next.store(true);
        bool rejected = false;
        try { p.QueueOptimizedPipeline(11); }
        catch (const std::runtime_error&) { rejected = true; }
        assert(rejected && !p.optimize_state->running);
    }
}
"""

with tempfile.TemporaryDirectory(prefix="eden-r313-pipelines-") as d:
    source = Path(d) / "worker.cpp"
    app = Path(d) / "worker"
    source.write_text(code)
    subprocess.run(["c++", "-std=c++20", "-O2", "-pthread", "-Wall", "-Wextra",
                    "-Werror", str(source), "-o", str(app)], check=True, timeout=40)
    subprocess.run([str(app)], check=True, timeout=20)
print("PASS F07 initial builder teardown, optimizer queued lifetime, cancel, null handle, rejection, release/acquire")
print("PASS R313 runtime-only fast-first, disk cache exclusion, one worker, no OOB index 24")
