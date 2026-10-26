#!/usr/bin/env python3
"""Compile and execute the actual F07 Vulkan compute wait callback in two races.

If shader completion precedes callback dispatch, do not grab the pipeline
build mutex. If not completed, retain the condition-variable wait in order.
Graphics already implements the same release/acquire fast path.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()
graphics = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
start = "        scheduler.Record([this](vk::CommandBuffer) {"
end = "\n        });"
assert source.count(start) == 1
callback = start + source.split(start, 1)[1].split(end, 1)[0] + end
assert callback.count("is_built.load(std::memory_order_acquire)") == 1
assert callback.index("is_built.load(std::memory_order_acquire)") < callback.index("std::unique_lock lock{build_mutex};")
assert "build_condvar.wait(lock, [this] { return is_built.load(std::memory_order::relaxed); });" in callback
assert "is_built.store(true, std::memory_order_release);" in source
assert "if (is_built.load(std::memory_order_acquire)) return;" in graphics
assert "if name in ('vk_graphics_pipeline', 'vk_compute_pipeline'):" in generator

cpp = r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>
namespace vk { struct CommandBuffer {}; }
namespace Eden::Performance { struct VulkanTimer { explicit VulkanTimer(int) {} }; }
struct CountingMutex {
    std::mutex inner;
    std::atomic<int> lock_calls{0};
    void lock() { ++lock_calls; inner.lock(); }
    void unlock() { inner.unlock(); }
};
struct Scheduler {
    std::function<void(vk::CommandBuffer)> queued;
    template<class F> void Record(F&& fn) { queued = std::forward<F>(fn); }
    void run() { assert(queued); queued(vk::CommandBuffer{}); }
};
struct Compute {
    Scheduler scheduler;
    CountingMutex build_mutex;
    std::condition_variable_any build_condvar;
    std::atomic_bool is_built{false};
    int pipeline{};
    void Queue() {
        if (!is_built.load(std::memory_order_acquire)) {
""" + callback + r"""
        }
    }
    void Publish(bool built) {
        { std::unique_lock lock{build_mutex};
          pipeline = built ? 93 : 0;
          is_built.store(true, std::memory_order_release);
        }
        build_condvar.notify_all();
    }
};
int main() {
    for (int i = 0; i < 120; ++i) {
        Compute c;
        c.Queue();
        std::thread producer([&] { c.Publish(true); });
        producer.join();
        c.build_mutex.lock_calls.store(0);
        c.scheduler.run();
        assert(c.build_mutex.lock_calls.load() == 0);
        assert(c.pipeline == 93);
    }
    for (int i = 0; i < 120; ++i) {
        Compute c;
        c.Queue();
        std::thread producer([&] {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            c.Publish(true);
        });
        c.scheduler.run();
        producer.join();
        assert(c.build_mutex.lock_calls.load() >= 1);
        assert(c.pipeline == 93);
    }
    Compute failed;
    failed.Queue();
    failed.Publish(false);
    failed.build_mutex.lock_calls.store(0);
    failed.scheduler.run();
    assert(failed.build_mutex.lock_calls.load() == 0);
    assert(failed.pipeline == 0);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++ compiler missing"
with tempfile.TemporaryDirectory(prefix="encore-f07-compute-ready-") as d:
    file = Path(d) / "test.cpp"
    file.write_text(cpp)
    for optimization in ("-O0", "-O2"):
        executable = Path(d) / ("test-" + optimization[1:])
        subprocess.run([compiler, "-std=c++20", optimization, "-pthread",
                        "-Wall", "-Wextra", "-Werror", str(file), "-o", str(executable)],
                       check=True, capture_output=True, text=True, timeout=40)
        subprocess.run([str(executable)], check=True, timeout=25)
print("F07_COMPUTE_READY_CALLBACK_PASS release_acquire=1 short_circuit=1 unfinished_wait=1 O0=1 O2=1")
