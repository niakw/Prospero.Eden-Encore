#!/usr/bin/env python3
"""R421: bound speculative Vulkan optimization behind real first-use builds."""
import ast
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
vulkan = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
ast.parse(generator)
assert '#include <atomic>' in vulkan
assert '#include <chrono>' in vulkan
assert '#include <thread>' in vulkan
assert 'std::atomic<unsigned> pending_first_use_graphics_builds{0};' in vulkan
assert 'if (::Eden::DevVulkan::fast_first_pipelines) {' in vulkan
assert 'pending_first_use_graphics_builds.fetch_add(1, std::memory_order_release);' in vulkan
assert vulkan.count('pending_first_use_graphics_builds.fetch_sub(1, std::memory_order_release);') == 2
assert 'worker_thread->QueueWork([build = std::move(func)]() mutable {' in vulkan
assert 'SCOPE_EXIT {' in vulkan
assert 'std::chrono::milliseconds(48)' in vulkan
assert 'std::this_thread::sleep_for(std::chrono::milliseconds(2));' in vulkan
assert '::Eden::Performance::ProbeSchedulerOnce("VkPipelineOptimize");' in vulkan
assert '::Eden::Performance::ProbeSchedulerOnce("VkPipelineOptimize");' in generator
assert 'const auto until = std::chrono::steady_clock::now()' in generator
assert 'pending_first_use_graphics_builds' in generator
assert 'std::chrono::milliseconds(48)' in generator
assert vulkan.index('const auto until = std::chrono::steady_clock::now()') < vulkan.index(
    'if (state->cancelled) return;', vulkan.index('void GraphicsPipeline::QueueOptimizedPipeline'))
# Test the *actual checked-in gate body*, not a separately implemented algorithm.
start = vulkan.index('        const auto until = std::chrono::steady_clock::now()')
end = vulkan.index('\n#endif', start)
gate = vulkan[start:end]
assert gate.count('pending_first_use_graphics_builds.load') == 1
assert gate.count('std::this_thread::sleep_for') == 1
cpp = """
#include <atomic>
#include <chrono>
#include <thread>
#include <cassert>
using namespace std::chrono;
std::atomic<unsigned> pending_first_use_graphics_builds{0};
void defer_optimizer() {
""" + gate + """
}
int main() {
    pending_first_use_graphics_builds.store(1);
    std::thread release([] {
        std::this_thread::sleep_for(std::chrono::milliseconds(12));
        pending_first_use_graphics_builds.store(0, std::memory_order_release);
    });
    auto before = steady_clock::now();
    defer_optimizer();
    auto elapsed = duration_cast<milliseconds>(steady_clock::now()-before).count();
    release.join();
    assert(elapsed >= 6 && elapsed < 150);
    pending_first_use_graphics_builds.store(1);
    before = steady_clock::now();
    defer_optimizer();
    elapsed = duration_cast<milliseconds>(steady_clock::now()-before).count();
    assert(elapsed >= 40 && elapsed < 250);
    pending_first_use_graphics_builds.store(0);
    before = steady_clock::now();
    defer_optimizer();
    assert(duration_cast<milliseconds>(steady_clock::now()-before).count() < 100);
}
"""
compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
assert compiler, "host C++ compiler needed for fairness timing fixture"
with tempfile.TemporaryDirectory(prefix="eden-pipeline-fairness-") as temp:
    source = Path(temp) / "probe.cpp"
    binary = Path(temp) / "probe"
    source.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O2", "-pthread", str(source), "-o", str(binary)],
                   check=True, timeout=90)
    subprocess.run([str(binary)], check=True, timeout=90)
print("PASS: R421 first-use graphics priority, bounded optimizer defer, no render-path sleep")
