#!/usr/bin/env python3
"""Compile the real graphics pipeline ready-wait callback from the active fork.

When an async pipeline completes before queued GPU commands run, the callback
must not acquire a native lock. When incomplete it must still wait for the
builder's release publication. Models host callback behavior, NOT PS5 FPS.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC=(ROOT/"vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
GEN=(ROOT/"tools/prepare-vulkan-port.py").read_text()
start=SRC.index("        scheduler.Record([this](vk::CommandBuffer) {\n")
end=SRC.index("\n        });",start) + len("\n        });")
snippet=SRC[start:end]
assert SRC.count("        scheduler.Record([this](vk::CommandBuffer) {\n") == 1
assert "if (is_built.load(std::memory_order_acquire)) return;" in snippet
acquire = "is_built.load(std::memory_order_acquire)"
assert snippet.count(acquire) == 2
first = snippet.index(acquire)
second = snippet.index(acquire, first + len(acquire))
mutex = snippet.index("std::unique_lock lock{build_mutex};")
timer = snippet.index("CachePhase::GraphicsPipelineWait")
assert first < mutex < second < timer
assert snippet.index("#ifdef PS5_NATIVE", first) < mutex
assert snippet.index("#ifndef PS5_NATIVE", timer) > timer
assert snippet.count("CachePhase::GraphicsPipelineWait") == 1
assert "build_condvar.wait(lock, [this] { return is_built.load(std::memory_order::relaxed); });" in snippet
assert 'Builder published the pipeline before this ordered GPU callback' in GEN

CPP=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>
namespace vk { using CommandBuffer = int; }
namespace Eden::Performance {
struct VulkanTimer { explicit VulkanTimer(int) {} ~VulkanTimer() {} void reset() {} };
enum class CachePhase { GraphicsPipelineWait };
inline std::atomic<bool> detailed_gpu_profile{true};
inline std::atomic<unsigned> measured_waits{0};
inline std::atomic<unsigned> completed_traces{0};
struct PipelineWaitTrace {
    // Source-extracted release/acquire tests keep diagnostics inert.
    // The keyed V01 source witness separately compiles the real timer.
    void MarkLockAcquired() noexcept {}
    void Complete(const char*, std::uint64_t, bool) {
        completed_traces.fetch_add(1, std::memory_order_relaxed);
    }
};
struct CachePhaseTimer {
    explicit CachePhaseTimer(CachePhase, bool active) {
        if (active) measured_waits.fetch_add(1, std::memory_order_relaxed);
    }
    void Stop() {}
};
}
struct CountingMutex {
    std::mutex internal;
    std::atomic<unsigned> count{0};
    std::function<void()> before_lock;
    void lock() {
        count.fetch_add(1, std::memory_order_relaxed);
        auto hook = std::move(before_lock);
        if (hook) hook();
        internal.lock();
    }
    void unlock() { internal.unlock(); }
};
struct Scheduler {
    std::vector<std::function<void(vk::CommandBuffer)>> queued;
    template <class F> void Record(F&& fn) {
        queued.emplace_back(std::forward<F>(fn));
    }
};
struct Probe {
    std::atomic<bool> is_built{false};
    CountingMutex build_mutex;
    std::condition_variable_any build_condvar;
    Scheduler scheduler;
    struct Key { std::uint64_t Hash() const { return 0xBEEF; } } key;
    bool CanExecuteDraw() const { return is_built.load(std::memory_order_acquire); }
    void Publish() {
        { std::scoped_lock lock{build_mutex};
          is_built.store(true, std::memory_order_release); }
        build_condvar.notify_all();
    }
    void Queue() {
        if (!is_built.load(std::memory_order::relaxed)) {
INJECT
        }
    }
};
int main() {
    { Probe p; p.Publish(); p.Queue(); assert(p.scheduler.queued.empty()); }
    for (int i = 0; i < 120; ++i) {
        Probe p; p.Queue(); assert(p.scheduler.queued.size() == 1);
        p.Publish(); p.build_mutex.count.store(0);
        p.scheduler.queued[0](0);
        assert(p.build_mutex.count.load() == 0);
    }
    assert(Eden::Performance::measured_waits.load() == 0);
    // Force publication between the first acquire and the native mutex recheck.
    {
        Probe p; p.Queue();
        p.build_mutex.before_lock = [&p] {
            std::thread([&p] { p.Publish(); }).join();
        };
        p.scheduler.queued[0](0);
        assert(p.build_mutex.count.load() == 2);
#ifdef PS5_NATIVE
        assert(Eden::Performance::measured_waits.load() == 0);
#else
        assert(Eden::Performance::measured_waits.load() == 1);
#endif
        assert(Eden::Performance::completed_traces.load() == 0);
    }
    const auto baseline = Eden::Performance::measured_waits.load();
    for (int i = 0; i < 120; ++i) {
        Probe p; p.Queue();
        const auto before = Eden::Performance::measured_waits.load();
        std::thread publisher([&] {
            while (Eden::Performance::measured_waits.load() == before)
                std::this_thread::yield();
            p.Publish();
        });
        p.scheduler.queued[0](0);
        publisher.join();
        assert(p.build_mutex.count.load() >= 1);
    }
    assert(Eden::Performance::measured_waits.load() == baseline + 120);
#ifdef PS5_NATIVE
    assert(Eden::Performance::completed_traces.load() == 120);
#else
    assert(Eden::Performance::completed_traces.load() == 0);
#endif
    Eden::Performance::detailed_gpu_profile.store(false);
    {
        Probe p; p.Queue();
        std::thread publisher([&] {
            while (p.build_mutex.count.load() == 0)
                std::this_thread::yield();
            p.Publish();
        });
        p.scheduler.queued[0](0);
        publisher.join();
        assert(Eden::Performance::measured_waits.load() == baseline + 120);
    }
}
""".replace("INJECT",snippet)
compiler=os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="eden-pipeline-ready-wait-") as tmp:
    p=Path(tmp)
    src=p/"fixture.cpp"
    src.write_text(CPP)
    for native in (False, True):
        for opt in ("-O0", "-O2"):
            binary=p/("fixture-"+("native" if native else "desktop")+opt[1:])
            command=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror","-pthread",
                     "-fsanitize=address,undefined","-fno-sanitize-recover=all"]
            if native:
                command.append("-DPS5_NATIVE")
            command.extend([str(src),"-o",str(binary)])
            subprocess.run(command,check=True,capture_output=True,text=True,timeout=60)
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30)
            assert result.returncode == 0, (native,opt,result.returncode,result.stdout[-800:],result.stderr[-2000:])
print("ENCORE_PIPELINE_READY_WAIT_HOST_PASS native_desktop=1 O0_O2=1 publication_race=1 quiet=1")
