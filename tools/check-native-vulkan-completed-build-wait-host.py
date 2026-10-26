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
assert snippet.index("std::memory_order_acquire") < snippet.index("CachePhase::GraphicsPipelineWait") < snippet.index("std::unique_lock lock{build_mutex}")
assert snippet.count("CachePhase::GraphicsPipelineWait") == 1
assert "build_condvar.wait(lock, [this] { return is_built.load(std::memory_order::relaxed); });" in snippet
assert 'Builder published the pipeline before this ordered GPU callback' in GEN

CPP=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>
namespace vk { using CommandBuffer = int; }
namespace Eden::Performance {
struct VulkanTimer { explicit VulkanTimer(int) {} };
enum class CachePhase { GraphicsPipelineWait };
inline std::atomic<bool> detailed_gpu_profile{true};
inline std::atomic<unsigned> measured_waits{0};
struct CachePhaseTimer {
    explicit CachePhaseTimer(CachePhase, bool active) {
        if (active) measured_waits.fetch_add(1, std::memory_order_relaxed);
    }
};
}
struct CountingMutex {
    std::mutex internal;
    std::atomic<unsigned> count{0};
    void lock() { count.fetch_add(1, std::memory_order_relaxed); internal.lock(); }
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
    void Queue() {
        if (!is_built.load(std::memory_order::relaxed)) {
INJECT
        }
    }
};
int main() {
    {
        Probe p;
        p.is_built.store(true, std::memory_order_release);
        p.Queue();
        assert(p.scheduler.queued.empty());
    }
    {
        Probe p;
        p.Queue();
        assert(p.scheduler.queued.size() == 1);
        // Builder completed before the GPU callback was processed.
        p.is_built.store(true, std::memory_order_release);
        p.scheduler.queued[0](0);
        assert(p.build_mutex.count.load() == 0);
        assert(Eden::Performance::measured_waits.load() == 0);
    }
    {
        Probe p;
        p.Queue();
        std::atomic<bool> returned{false};
        std::thread worker([&] {
            p.scheduler.queued[0](0);
            returned.store(true);
        });
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        while (!p.build_mutex.count.load() && std::chrono::steady_clock::now() < deadline)
            std::this_thread::yield();
        const bool took_lock = p.build_mutex.count.load() > 0;
        // Builder still owns the original publication/wakeup protocol.
        {
            std::scoped_lock lock{p.build_mutex};
            p.is_built.store(true, std::memory_order_release);
        }
        p.build_condvar.notify_all();
        worker.join();
        assert(took_lock && returned.load());
        assert(Eden::Performance::measured_waits.load() == 1);
    }
    {
        Eden::Performance::detailed_gpu_profile.store(false);
        Probe p;
        p.Queue();
        std::thread publisher([&] {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            { std::scoped_lock lock{p.build_mutex};
              p.is_built.store(true, std::memory_order_release); }
            p.build_condvar.notify_all();
        });
        p.scheduler.queued[0](0);
        publisher.join();
        assert(Eden::Performance::measured_waits.load() == 1);
    }
}
""".replace("INJECT",snippet)
compiler=os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="eden-pipeline-ready-wait-") as tmp:
    p=Path(tmp)
    src=p/"fixture.cpp"
    bin=p/"fixture"
    src.write_text(CPP)
    subprocess.run(
        [compiler,"-std=c++20","-O1","-Wall","-Wextra","-pthread",
         "-fsanitize=address,undefined","-fno-sanitize-recover=all",
         str(src),"-o",str(bin)],
        check=True,capture_output=True,text=True,timeout=60)
    result=subprocess.run([str(bin)],capture_output=True,text=True,timeout=20)
    assert result.returncode == 0, (result.returncode,result.stdout[-800:],result.stderr[-2000:])
print("ENCORE_PIPELINE_READY_WAIT_HOST_PASS completed_fast_path=1 active_build_wait=1")
