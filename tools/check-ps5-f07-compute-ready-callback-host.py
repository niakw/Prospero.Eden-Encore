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
# Native V01 rechecks publication under build_mutex before starting any timer.
# Desktop keeps the original single acquire and timer-before-lock ordering.
acquires = "is_built.load(std::memory_order_acquire)"
assert callback.count(acquires) == 2
first = callback.index(acquires)
second = callback.index(acquires, first + len(acquires))
mutex = callback.index("std::unique_lock lock{build_mutex};")
timer = callback.index("CachePhase::ComputePipelineWait")
assert first < mutex < second < timer
assert callback.index("#ifdef PS5_NATIVE", first) < mutex
assert callback.index("#ifndef PS5_NATIVE", timer) > timer
assert callback.count("CachePhase::ComputePipelineWait") == 1
assert "build_condvar.wait(lock, [this] { return is_built.load(std::memory_order::relaxed); });" in callback
assert "is_built.store(true, std::memory_order_release);" in source
assert "if (is_built.load(std::memory_order_acquire)) return;" in graphics
assert "if name in ('vk_graphics_pipeline', 'vk_compute_pipeline'):" in generator

cpp = r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>
namespace vk { struct CommandBuffer {}; }
// Real VulkanTimer is RAII and therefore not a trivial throwaway local.
// Mirror its destructor so -Werror does not reject the source-extracted timer.
namespace Eden::Performance {
struct VulkanTimer { explicit VulkanTimer(int) {} ~VulkanTimer() {} void reset() {} };
enum class CachePhase { ComputePipelineWait };
inline std::atomic<bool> detailed_gpu_profile{true};
inline std::atomic<unsigned> measured_waits{0};
inline std::atomic<unsigned> completed_traces{0};
struct PipelineWaitTrace {
    // The real V01 trace measures the lock phase; this fixture only
    // verifies release/acquire publication and the optional early exit.
    void MarkLockAcquired() noexcept {}
    void Complete(const char*, std::uint64_t, bool) {
        completed_traces.fetch_add(1, std::memory_order_relaxed);
    }
};
struct CachePhaseTimer {
    explicit CachePhaseTimer(CachePhase, bool enabled) {
        if (enabled) measured_waits.fetch_add(1, std::memory_order_relaxed);
    }
    void Stop() {}
};
}
struct CountingMutex {
    std::mutex inner;
    std::atomic<int> lock_calls{0};
    std::function<void()> before_lock;
    void lock() {
        ++lock_calls;
        auto hook = std::move(before_lock);
        if (hook) hook();
        inner.lock();
    }
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
    std::uint64_t diagnostic_cache_key_hash{0xC0FFEE};
    bool IsBound() const { return pipeline != 0; }
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
    assert(Eden::Performance::measured_waits.load() == 0);
    // Force publication between the first acquire and the mutex recheck.
    // The hook runs before the callback acquires build_mutex; Publish uses
    // the same mutex, then the callback observes the completed build.
    {
        Compute c;
        c.Queue();
        c.build_mutex.before_lock = [&c] {
            std::thread([&c] { c.Publish(true); }).join();
        };
        c.scheduler.run();
        assert(c.pipeline == 93);
        assert(c.build_mutex.lock_calls.load() == 2);
#ifdef PS5_NATIVE
        assert(Eden::Performance::measured_waits.load() == 0);
#else
        // The desktop timer intentionally retains its pre-lock placement.
        assert(Eden::Performance::measured_waits.load() == 1);
#endif
        assert(Eden::Performance::completed_traces.load() == 0);
    }
    const auto wait_baseline = Eden::Performance::measured_waits.load();
    for (int i = 0; i < 120; ++i) {
        Compute c;
        c.Queue();
        const auto previous = Eden::Performance::measured_waits.load();
        std::thread producer([&] {
            // Do not race the first acquire: publish only after the timer
            // proves the callback actually reached its wait path.
            while (Eden::Performance::measured_waits.load() == previous)
                std::this_thread::yield();
            c.Publish(true);
        });
        c.scheduler.run();
        producer.join();
        assert(c.build_mutex.lock_calls.load() >= 1);
        assert(c.pipeline == 93);
    }
    assert(Eden::Performance::measured_waits.load() == wait_baseline + 120);
#ifdef PS5_NATIVE
    assert(Eden::Performance::completed_traces.load() == 120);
#else
    assert(Eden::Performance::completed_traces.load() == 0);
#endif
    Eden::Performance::detailed_gpu_profile.store(false);
    {
        Compute c;
        c.Queue();
        std::thread producer([&] {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            c.Publish(true);
        });
        c.scheduler.run();
        producer.join();
        assert(c.pipeline == 93);
        assert(Eden::Performance::measured_waits.load() == wait_baseline + 120);
    }
    Compute failed;
    failed.Queue();
    failed.Publish(false);
    failed.build_mutex.lock_calls.store(0);
    failed.scheduler.run();
    assert(failed.build_mutex.lock_calls.load() == 0);
    assert(failed.pipeline == 0);
    assert(Eden::Performance::measured_waits.load() == wait_baseline + 120);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++ compiler missing"
with tempfile.TemporaryDirectory(prefix="encore-f07-compute-ready-") as d:
    file = Path(d) / "test.cpp"
    file.write_text(cpp)
    for native in (False, True):
        for optimization in ("-O0", "-O2"):
            executable = Path(d) / ("test-" + ("native-" if native else "desktop-") + optimization[1:])
            command = [compiler, "-std=c++20", optimization, "-pthread",
                       "-Wall", "-Wextra", "-Werror"]
            if native:
                command.append("-DPS5_NATIVE")
            command.extend([str(file), "-o", str(executable)])
            subprocess.run(command, capture_output=True, text=True, timeout=40, check=True)
            subprocess.run([str(executable)], check=True, timeout=25)
print("F07_COMPUTE_READY_CALLBACK_PASS native_desktop=1 second_acquire=1 publication_race=1 quiet=1 O0=1 O2=1")
