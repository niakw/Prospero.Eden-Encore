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
# The generated optimizer body receives one reviewed late delta: it
# observes both graphics and compute cold-build backlogs. Compare the
# post-delta implementation instead of the original generator literal.
old_gate = "while (pending_first_use_graphics_builds.load(std::memory_order_acquire) != 0) {"
new_gate = ("while (pending_first_use_graphics_builds.load(std::memory_order_acquire) != 0 ||\n"
            "               pending_first_use_compute_builds.load(std::memory_order_acquire) != 0) {")
assert worker.count(old_gate) == 1
# The second reviewed late delta turns the counter wait into an
# idle-window loop. Reapply both generator deltas in order before comparison.
source_body = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
old_body = "        while (pending_first_use_graphics_builds.load(std::memory_order_acquire) != 0 ||\n               pending_first_use_compute_builds.load(std::memory_order_acquire) != 0) {\n            {\n                std::scoped_lock lock{state->mutex};\n                if (state->cancelled) return;\n            }\n            std::this_thread::sleep_for(std::chrono::milliseconds(2));\n        }"
new_body = "        // A momentarily empty builder queue is not an idle GPU frame.\n        // Require a brief QUIET period before any OPTIONAL driver rebuild:\n        // new HUD shaders appearing in a burst reset the countdown. This\n        // sleep is confined to the optimizer worker, never the GPU owner.\n        constexpr auto quiet_window = std::chrono::milliseconds(16);\n        auto quiet_since = std::chrono::steady_clock::now();\n        for (;;) {\n            const bool cold_build_pending =\n                pending_first_use_graphics_builds.load(std::memory_order_acquire) != 0 ||\n                pending_first_use_compute_builds.load(std::memory_order_acquire) != 0;\n            if (cold_build_pending) {\n                quiet_since = std::chrono::steady_clock::now();\n            } else if (std::chrono::steady_clock::now() - quiet_since >= quiet_window) {\n                break;\n            }\n            {\n                std::scoped_lock lock{state->mutex};\n                if (state->cancelled) return;\n            }\n            std::this_thread::sleep_for(std::chrono::milliseconds(2));\n        }"
assert 'F07 quiet-window priority between cold pipeline bursts' in generator
assert worker.count(old_gate) == 1
# Reconstruct the selected optimizer after the reviewed generator deltas,
# including the PS5-only admission cap. Comparing the original R313 literal
# directly would reject a correctly regenerated source after these changes.
generated_worker = worker.replace(old_gate, new_gate).replace(old_body, new_body)
backlog_delta_names = {
    "F07 bound optional Vulkan optimizer queue helper",
    "F07 skip overloaded optional pipeline builds before allocation",
    "F07 release optional pipeline slot on completion or cancellation",
    "F07 hand off optional pipeline slot after successful queue admission",
}
applied_backlog_deltas = set()
for node in nodes:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        continue
    call = node.value
    if not isinstance(call.func, ast.Name) or call.func.id != "apply_reviewed_delta":
        continue
    if len(call.args) != 4:
        continue
    try:
        name = ast.literal_eval(call.args[3])
    except (ValueError, TypeError):
        continue
    if name not in backlog_delta_names:
        continue
    assert ast.literal_eval(call.args[0]) == "vk_graphics_pipeline_cost.cpp"
    before = ast.literal_eval(call.args[1])
    after = ast.literal_eval(call.args[2])
    assert generated_worker.count(before) == 1, name
    assert after not in generated_worker, name
    generated_worker = generated_worker.replace(before, after)
    assert name not in applied_backlog_deltas
    applied_backlog_deltas.add(name)
assert applied_backlog_deltas == backlog_delta_names
assert generated_worker in source_body
assert "F07 optimized graphics yields to compute builds" in generator
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


# Compile the actual default/reset contract on native release and non-native
# profiles. The fast-first feature has a runtime opt-out; it must reset to
# the profile default only when the next title begins.
header = (root / "headless/dev_vulkan.h").read_text()
assert header.count("#if defined(PS5_NATIVE) || defined(EDEN_DEV_PROFILE)") == 2
default_probe = r"""
#include <cassert>
#include <cstdio>
#include "headless/dev_vulkan.h"
int main() {
#if defined(PS5_NATIVE) || defined(EDEN_DEV_PROFILE)
    constexpr bool expected = true;
#else
    constexpr bool expected = false;
#endif
    using namespace Eden::DevVulkan;
    assert(fast_first_pipelines == expected);
    fast_first_pipelines = !expected;
    assert(fast_first_pipelines != expected);
    ResetForTitle();
    assert(fast_first_pipelines == expected);
    fast_first_pipelines = false;
    assert(!fast_first_pipelines);
    ResetForTitle();
    assert(fast_first_pipelines == expected);
    std::puts("FAST_FIRST_DEFAULT_PROFILE_PASS");
}
"""
with tempfile.TemporaryDirectory(prefix="encore-f07-fast-first-default-") as d:
    probe_source = Path(d) / "defaults.cpp"
    probe_source.write_text(default_probe)
    for label, macros in (
        ("native-release", ["-DPS5_NATIVE=1"]),
        ("native-dev", ["-DPS5_NATIVE=1", "-DEDEN_DEV_PROFILE=1"]),
        ("desktop-release", []),
        ("desktop-dev", ["-DEDEN_DEV_PROFILE=1"]),
    ):
        for optimization in ("-O0", "-O2"):
            binary = Path(d) / (label + optimization[1:])
            subprocess.run(["c++", "-std=c++20", optimization,
                            "-Wall", "-Wextra", "-Werror", "-I", str(root),
                            *macros, str(probe_source), "-o", str(binary)],
                           check=True, capture_output=True, text=True, timeout=40)
            result = subprocess.run([str(binary)], check=True,
                                    capture_output=True, text=True, timeout=15)
            assert "FAST_FIRST_DEFAULT_PROFILE_PASS" in result.stdout
            print("FAST_FIRST_DEFAULT_PROFILE_PASS", label, optimization)


# The dev A/B parser is compiled out of shipping native release. Keep one
# narrow, file-backed opt-out for the newly enabled default, without opening
# the general development switches in retail packages.
const_main = (root / "headless/main.cpp").read_text()
release_start = "#if defined(PS5_NATIVE) && !defined(EDEN_DEV_PROFILE)\n        // Shipping native release keeps fast-first enabled"
assert const_main.count(release_start) == 1
start = const_main.index(release_start)
stop = const_main.index("\n#endif", start) + len("\n#endif")
release_override = const_main[start:stop]
assert 'std::filesystem::path{Eden::ConfigDir()} / "fast-pipelines.txt"' in release_override
assert 'pipeline_option >> selected && selected == "off"' in release_override
assert "Eden::DevVulkan::ResetForTitle();" in release_override
assert release_override.index("ResetForTitle();") < release_override.index("pipeline_option >>")
retail_probe = r"""
#include <cassert>
#include <filesystem>
#include <fstream>
#include <string>
#include "headless/dev_vulkan.h"
std::filesystem::path test_root;
namespace Eden {
std::string ConfigDir() { return test_root.string(); }
}
void ReadProfile() {
""" + release_override + r"""
}
int main(int argc, char** argv) {
    assert(argc == 2);
    test_root = argv[1];
    using namespace Eden::DevVulkan;
    ReadProfile();
    assert(fast_first_pipelines);
    {
        std::ofstream out(test_root / "fast-pipelines.txt");
        out << "off\n";
    }
    ReadProfile();
    assert(!fast_first_pipelines);
    {
        std::ofstream out(test_root / "fast-pipelines.txt");
        out << "on\n";
    }
    ReadProfile();
    assert(fast_first_pipelines);
    std::filesystem::remove(test_root / "fast-pipelines.txt");
    ReadProfile();
    assert(fast_first_pipelines);
}
"""
with tempfile.TemporaryDirectory(prefix="encore-f07-retail-fast-optout-") as d:
    program = Path(d) / "retail.cpp"
    program.write_text(retail_probe)
    for optimization in ("-O0", "-O2"):
        binary = Path(d) / ("retail" + optimization[1:])
        subprocess.run(["c++", "-std=c++20", "-DPS5_NATIVE=1", optimization,
                        "-Wall", "-Wextra", "-Werror", "-I", str(root),
                        str(program), "-o", str(binary)],
                       check=True, capture_output=True, text=True, timeout=40)
        subprocess.run([str(binary), d], check=True, timeout=15)
        print("FAST_FIRST_RELEASE_OVERRIDE_PASS", optimization)
