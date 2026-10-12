#!/usr/bin/env python3
"""R357: native Vulkan Scheduler drain notifications, exact-source host fixture."""
from pathlib import Path
import subprocess
import shutil
import tempfile
import ast

root = Path(__file__).resolve().parents[1]
header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_scheduler.h").read_text()
source = (root / "vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
ast.parse(generator)
assert "unsigned queue_drain_waiters{};" in header
assert "++queue_drain_waiters;" in source
assert "--queue_drain_waiters;" in source
assert "if (work_queue.empty() && queue_drain_waiters != 0)" in source
assert "event_cv.notify_all();" in source
assert "queue_drain_waiters" in generator
# Capture the actual production WaitWorker body and queue-pop lambda rather
# than silently testing a separately retyped version.
wait_start = source.index("void Scheduler::WaitWorker() {")
wait_end = source.index("\nvoid Scheduler::DispatchWork()", wait_start)
native_wait = source[wait_start:wait_end]
worker_start = source.index("    const auto TryPopQueue{[this](auto& work) -> bool {")
worker_end = source.index("\n    while (!stop_token.stop_requested())", worker_start)
native_pop = source[worker_start:worker_end]
cpp = r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <future>
#include <memory>
#include <mutex>
#include <queue>
#include <stop_token>
#include <thread>
#include <vector>
#include <cstdio>
using namespace std::chrono_literals;
struct CommandChunk { unsigned sequence; };
class Scheduler {
public:
    std::queue<std::unique_ptr<CommandChunk>> work_queue;
    std::mutex queue_mutex, execution_mutex;
    std::condition_variable_any event_cv;
    unsigned queue_drain_waiters{};
    std::atomic<unsigned> executed{0};
    std::atomic<unsigned> empty_notifications{0};
    std::jthread worker;
    Scheduler() : worker([this](std::stop_token token) { WorkerThread(token); }) {}
    ~Scheduler() {
        worker.request_stop();
        event_cv.notify_all();
        worker.join();
    }
    void DispatchWork() {}
    void WaitWorker();
    void Enqueue(unsigned sequence) {
        { std::lock_guard lock{queue_mutex};
          work_queue.push(std::make_unique<CommandChunk>(sequence));
        }
        event_cv.notify_all();
    }
    void WorkerThread(std::stop_token stop_token) {
__NATIVE_POP__
        while (!stop_token.stop_requested()) {
            std::unique_ptr<CommandChunk> work;
            { std::unique_lock lock{queue_mutex};
              event_cv.wait(lock, stop_token, [&] { return TryPopQueue(work); });
              if (stop_token.stop_requested()) return;
            }
            { std::lock_guard lock{execution_mutex};
              assert(work->sequence == executed.fetch_add(1));
            }
        }
    }
};
__NATIVE_WAIT__
int main() {
    Scheduler scheduler;
    constexpr unsigned rounds = 100, each = 40;
    for (unsigned batch = 0; batch < rounds; ++batch) {
        for (unsigned i=0; i<each; ++i) scheduler.Enqueue(batch*each + i);
        // WaitWorker can start while the worker is actively popping.
        auto completion = std::async(std::launch::async,
                                     [&] { scheduler.WaitWorker(); });
        assert(completion.wait_for(4s) == std::future_status::ready);
        completion.get();
        assert(scheduler.executed.load() == (batch+1)*each);
    }
    // WaitWorker must also return when queue already empty, without notification.
    scheduler.WaitWorker();
    assert(scheduler.queue_drain_waiters == 0);
    std::puts("PASS R357: source-replayed empty-drain waits, FIFO, no missed wakeups");
}
""".replace("__NATIVE_POP__", native_pop).replace("__NATIVE_WAIT__", native_wait)
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-r357-worker-") as tmp:
    path = Path(tmp) / "worker.cpp"
    exe = Path(tmp) / "worker"
    path.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O1", "-pthread",
                    "-Wall", "-Wextra", "-Werror", str(path), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], timeout=30, check=True)
print("Vulkan worker stop-notify remains unconditional; queue drain wakeups are conditional")
