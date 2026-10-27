#!/usr/bin/env python3
"""R444: prioritize first-use shader builds over optional Vulkan rebuilds."""
import ast
import shutil
import subprocess
import tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
vulkan = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
compute = (root / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
ast.parse(generator)
assert '#include <atomic>' in vulkan
assert 'std::atomic<unsigned> pending_first_use_graphics_builds{0};' in vulkan
# The native LTO link requires an exported Vulkan:: symbol, not an
# anonymous-namespace variable that happens to have the same spelling.
vulkan_namespace = vulkan.split('namespace Vulkan {', 1)[1].split('namespace {', 1)[0]
assert vulkan_namespace.count('std::atomic<unsigned> pending_first_use_graphics_builds{0};') == 1
assert vulkan.count('std::atomic<unsigned> pending_first_use_graphics_builds{0};') == 1
assert 'F07 graphics first-use counter exported at Vulkan namespace scope' in generator
assert 'pending_first_use_graphics_builds.fetch_add(1, std::memory_order_release);' in vulkan
assert vulkan.count('pending_first_use_graphics_builds.fetch_sub(1, std::memory_order_release);') == 2
assert 'worker_thread->QueueWork([build = std::move(func)]() mutable {' in vulkan
assert 'SCOPE_EXIT {' in vulkan
assert '::Eden::Performance::ProbeSchedulerOnce("VkPipelineOptimize");' in vulkan
assert '::Eden::Performance::ProbeSchedulerOnce("VkPipelineOptimize");' in generator
assert 'milliseconds(48)' not in vulkan
assert 'milliseconds(48)' not in generator
assert 'R444: Speculative rebuilds must not compete' in vulkan
assert 'R444: Speculative rebuilds must not compete' in generator
# Compile the exact production wait body with the author's cancellation protocol.
start = vulkan.index('        // R444: Speculative rebuilds must not compete')
end = vulkan.index('\n#endif', start)
gate = vulkan[start:end]
assert gate.count('pending_first_use_graphics_builds.load') == 1
assert gate.count('pending_first_use_compute_builds.load') == 1
assert 'extern std::atomic<unsigned> pending_first_use_compute_builds;' in vulkan
assert 'std::atomic<unsigned> pending_first_use_compute_builds{0};' in compute
assert 'F07 shared compute first-use backlog' in generator
assert 'F07 optimized graphics yields to compute builds' in generator
assert compute.count('pending_first_use_compute_builds.fetch_add(1, std::memory_order_release);') == 1
assert compute.count('pending_first_use_compute_builds.fetch_sub(1, std::memory_order_release);') == 2
assert compute.index('pending_first_use_compute_builds.fetch_add(1, std::memory_order_release);') < compute.index('thread_worker->QueueWork([build = std::move(func)]() mutable {')
assert gate.count('std::scoped_lock lock{state->mutex}') == 1
assert gate.count('if (state->cancelled) return;') == 1
assert gate.count('sleep_for') == 1
assert 'constexpr auto quiet_window = std::chrono::milliseconds(16);' in gate
assert 'quiet_since = std::chrono::steady_clock::now();' in gate
assert 'if (cold_build_pending)' in gate
assert 'F07 quiet-window priority between cold pipeline bursts' in generator
assert "F07 optimized graphics yields to compute builds" in generator
assert "pending_first_use_compute_builds.load(std::memory_order_acquire)" in generator
# The queued lifetime flag is now published BEFORE QueueWork, rather than
# when the worker starts. The fairness gate still checks cancellation before
# touching the owning pipeline, but must not assume the old flag placement.
queue_start = vulkan.index('void GraphicsPipeline::QueueOptimizedPipeline(VkRenderPass render_pass)')
queue_publish = vulkan.index('state->running = true;', queue_start)
queue_admit = vulkan.index('OptimizeWorker().QueueWork(', queue_start)
assert queue_publish < queue_admit < start
assert 'state->running = true;' not in gate
assert vulkan.index('if (state->cancelled) return;', start) < vulkan.index(
    'MakePipeline(render_pass, 0, &optimized_pipeline);', start)
cpp = """
#include <atomic>
#include <chrono>
#include <thread>
#include <cassert>
#include <mutex>
#include <memory>
using namespace std::chrono;
std::atomic<unsigned> pending_first_use_graphics_builds{0};
std::atomic<unsigned> pending_first_use_compute_builds{0};
struct State { std::mutex mutex; bool cancelled{false}; };
void defer_optimizer(std::shared_ptr<State> state) {
""" + gate + """
}
int main() {
    auto state = std::make_shared<State>();
    pending_first_use_graphics_builds.store(1);
    std::thread release([] {
        std::this_thread::sleep_for(30ms);
        pending_first_use_graphics_builds.store(0, std::memory_order_release);
    });
    auto before = steady_clock::now();
    defer_optimizer(state);
    auto elapsed = duration_cast<milliseconds>(steady_clock::now() - before).count();
    release.join();
    assert(elapsed >= 16 && elapsed < 250);
    // R421 used to begin competing after 48 ms even if first-use compilation
    // took longer. Remain idle until the remaining compilation is done.
    pending_first_use_graphics_builds.store(1);
    std::thread release_late([] {
        std::this_thread::sleep_for(100ms);
        pending_first_use_graphics_builds.store(0, std::memory_order_release);
    });
    before = steady_clock::now();
    defer_optimizer(state);
    elapsed = duration_cast<milliseconds>(steady_clock::now() - before).count();
    release_late.join();
    assert(elapsed >= 75 && elapsed < 300);
    // A title may close while another compilation never completes. Do not
    // strand its optimized pipeline worker or dereference a destroyed title.
    pending_first_use_graphics_builds.store(1);
    std::thread cancel([state] {
        std::this_thread::sleep_for(15ms);
        std::scoped_lock lock{state->mutex};
        state->cancelled = true;
    });
    before = steady_clock::now();
    defer_optimizer(state);
    elapsed = duration_cast<milliseconds>(steady_clock::now() - before).count();
    cancel.join();
    assert(elapsed >= 8 && elapsed < 150);
    // A cold compute build must delay speculative graphics just as a cold
    // graphics build does; foreground work has priority over background jobs.
    pending_first_use_graphics_builds.store(0);
    pending_first_use_compute_builds.store(1);
    std::thread release_compute([] {
        std::this_thread::sleep_for(65ms);
        pending_first_use_compute_builds.store(0, std::memory_order_release);
    });
    before = steady_clock::now();
    defer_optimizer(std::make_shared<State>());
    elapsed = duration_cast<milliseconds>(steady_clock::now() - before).count();
    release_compute.join();
    assert(elapsed >= 45 && elapsed < 260);
    // Cancellation must also free teardown when a compute compiler stalls.
    auto blocked = std::make_shared<State>();
    pending_first_use_compute_builds.store(1);
    std::thread cancel_compute([blocked] {
        std::this_thread::sleep_for(15ms);
        std::scoped_lock lock{blocked->mutex};
        blocked->cancelled = true;
    });
    before = steady_clock::now();
    defer_optimizer(blocked);
    elapsed = duration_cast<milliseconds>(steady_clock::now() - before).count();
    cancel_compute.join();
    assert(elapsed >= 8 && elapsed < 150);
    pending_first_use_compute_builds.store(0);
    pending_first_use_graphics_builds.store(0);
    before = steady_clock::now();
    defer_optimizer(std::make_shared<State>());
    elapsed = duration_cast<milliseconds>(steady_clock::now() - before).count();
    assert(elapsed >= 12 && elapsed < 120);
    // Reset the idle countdown when a burst of compute first-use begins
    // AFTER the optional graphics worker observed empty queues.
    std::thread transient([] {
        std::this_thread::sleep_for(7ms);
        pending_first_use_compute_builds.store(1, std::memory_order_release);
        std::this_thread::sleep_for(24ms);
        pending_first_use_compute_builds.store(0, std::memory_order_release);
    });
    before = steady_clock::now();
    defer_optimizer(std::make_shared<State>());
    elapsed = duration_cast<milliseconds>(steady_clock::now() - before).count();
    transient.join();
    assert(elapsed >= 38 && elapsed < 200);
}
"""
compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
assert compiler, "host C++ compiler required"
with tempfile.TemporaryDirectory(prefix="eden-r444-priority-") as directory:
    source = Path(directory) / "test.cpp"
    exe = Path(directory) / "test"
    source.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O2", "-pthread", str(source), "-o", str(exe)], check=True, timeout=90)
    subprocess.run([str(exe)], check=True, timeout=90)
print("R444: shader-first fair scheduler and teardown cancellation PASS")
