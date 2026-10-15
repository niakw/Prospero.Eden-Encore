#!/usr/bin/env python3
"""Compile exact native GPU producer method; host-only cancellation regression."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
base = root / "vendor/encore-active/eden-gpu"
quiet = (base / "gpu_thread_quiet.cpp").read_text()
dev = (base / "gpu_thread_dev.cpp").read_text()

def method(source):
    start = source.index("u64 ThreadManager::PushCommand(")
    end = source.index("\n\n} // namespace VideoCommon::GPUThread", start)
    return source[start:end]

for s in (quiet, dev):
    assert s.count('#include "gpu_failure.h"') == 2
    m = method(s)
    assert "const bool completed = state.cv.wait(lk, stop_source.get_token()" in m
    assert m.count("Eden::PeekGpuFailure()") == 2
    assert m.count("std::rethrow_exception(failure);") == 2
    assert m.count("return state.signaled_fence.load(std::memory_order_acquire);") == 2
    assert "if (!completed)" in m
    assert "if (!pushed)" in m

code = r"""
#include "gpu_failure.h"
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <exception>
#include <mutex>
#include <stdexcept>
#include <stop_token>
#include <thread>
#include <utility>
using u64 = std::uint64_t;
using CommandData = int;
struct CommandQueue {
    std::atomic<unsigned> enqueued{0};
    bool TryEmplace(CommandData&&, u64, bool) {
        enqueued.fetch_add(1, std::memory_order_release); return true;
    }
    bool EmplaceWaitWithStopToken(std::stop_token, CommandData&&, u64, bool) {
        assert(false && "test queue always has room"); return false;
    }
};
struct ThreadManager {
    struct {
        std::mutex write_lock;
        CommandQueue queue;
        u64 last_fence{};
        std::atomic<u64> signaled_fence{};
        std::condition_variable_any cv;
    } state;
    std::stop_source stop_source;
    u64 PushCommand(CommandData&& command_data, bool block, bool is_async);
};
__METHOD__
void await_enqueue(CommandQueue& q, unsigned count) {
    auto end = std::chrono::steady_clock::now() + std::chrono::seconds(1);
    while (q.enqueued.load(std::memory_order_acquire) < count &&
           std::chrono::steady_clock::now() < end) std::this_thread::yield();
    assert(q.enqueued.load(std::memory_order_acquire) >= count);
}
int main() {
    (void) Eden::TakeGpuFailure();
    ThreadManager normal;
    std::atomic<u64> normal_result{};
    std::thread completed([&] {
        normal_result.store(normal.PushCommand(1, true, false), std::memory_order_release);
    });
    await_enqueue(normal.state.queue, 1);
    normal.state.signaled_fence.store(1, std::memory_order_release);
    normal.state.cv.notify_all();
    completed.join();
    assert(normal_result.load() == 1);

    ThreadManager stopped;
    std::atomic<u64> cancelled_result{999};
    std::thread cancelled([&] {
        cancelled_result.store(stopped.PushCommand(2, true, false), std::memory_order_release);
    });
    await_enqueue(stopped.state.queue, 1);
    stopped.stop_source.request_stop();
    cancelled.join();
    assert(cancelled_result.load() == 0);
    assert(stopped.state.signaled_fence.load() == 0);
    assert(stopped.PushCommand(3, true, false) == 0);
    assert(stopped.state.queue.enqueued.load() == 1);

    ThreadManager failed;
    std::atomic<unsigned> failures{};
    auto waiter = [&](int command) {
        try { (void) failed.PushCommand(std::move(command), true, false); }
        catch (const std::runtime_error&) { failures.fetch_add(1); }
    };
    std::thread a(waiter, 4);
    std::thread b(waiter, 5);
    await_enqueue(failed.state.queue, 2);
    Eden::RecordGpuFailure(std::make_exception_ptr(std::runtime_error("GPU failed")));
    failed.stop_source.request_stop();
    a.join();
    b.join();
    assert(failures.load() == 2);
    assert(failed.state.signaled_fence.load() == 0);
    assert(Eden::PeekGpuFailure());
    bool saw_failure = false;
    try { (void) failed.PushCommand(6, true, false); }
    catch (const std::runtime_error&) { saw_failure = true; }
    assert(saw_failure);
    assert(failed.state.queue.enqueued.load() == 2);
    (void) Eden::TakeGpuFailure();
}
""".replace("__METHOD__", method(quiet))
with tempfile.TemporaryDirectory(prefix="eden-gpu-producer-") as d:
    src = Path(d) / "test.cpp"
    binary = Path(d) / "test"
    src.write_text(code)
    subprocess.run([
        "clang++", "-std=c++20", "-O1", "-g", "-pthread", "-Wall",
        "-Wextra", "-Werror", "-fsanitize=address,undefined",
        "-fno-sanitize-recover=all", "-I", str(root / "headless"),
        str(src), "-o", str(binary),
    ], check=True, timeout=45)
    subprocess.run([str(binary)], check=True, timeout=30)
print("GPU_PRODUCER_FATAL_WAIT_HOST_PASS completed=1 cancel_no_fake_fence=1 fatal_waiters=2 rejected_after_stop=1")
