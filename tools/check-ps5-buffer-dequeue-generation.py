#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prevent a producer wake from being consumed by only one guest buffer waiter.

This host test compiles the EXACT source methods from our pinned guest
BufferQueueCore. It proves multiwait notification semantics, not FC27 FPS.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cpp_path = root / "vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_core.cpp"
hdr_path = root / "vendor/sources/eden/src/core/hle/service/nvnflinger/buffer_queue_core.h"
graphics_path = root / "headless/graphics.cpp"
native_source = cpp_path.read_text()
native_header = hdr_path.read_text()
graphics = graphics_path.read_text()

assert "u64 dequeue_generation{};" in native_header
assert "std::atomic<bool> dequeue_possible" not in native_header
start = native_source.index("void BufferQueueCore::SignalDequeueCondition() {")
end = native_source.index("\ns32 BufferQueueCore::GetMinUndequeuedBufferCountLocked", start)
real_methods = native_source[start:end]
assert "++dequeue_generation;" in real_methods
assert "dequeue_generation != observed_generation" in real_methods
assert "dequeue_condition.notify_all();" in real_methods
assert "dequeue_possible.store(false)" not in real_methods

# Renderer callback may write buffered telemetry into an independent pipe,
# but must not forcibly flush or wait for file I/O in a frame callback.
render_start = graphics.index("void GraphicsWindow::OnFrameDisplayed() {")
render_end = graphics.index("\nvoid GraphicsWindow::CheckPresentation", render_start)
render_callback = graphics[render_start:render_end]
report_end = render_callback.index("Eden::Performance::ReportGpuThread(frame_total);")
next_branch = render_callback.index("} else {", report_end)
assert "std::fflush(stdout);" not in render_callback[report_end:next_branch]

fixture = r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <future>
#include <mutex>
#include <thread>
#include <vector>
#include <cstdio>
using u64=std::uint64_t;
class BufferQueueCore {
public:
    std::mutex mutex;
    std::condition_variable dequeue_condition;
    u64 dequeue_generation{};
    void SignalDequeueCondition();
    bool WaitForDequeueCondition(std::unique_lock<std::mutex>& lk);
};
__REAL_METHODS__
int main() {
    using namespace std::chrono_literals;
    // Every waiter is already checking availability while holding mutex.
    // A concurrent wake must become visible to ALL who release it in wait.
    for (int round=0; round<100; ++round) {
        BufferQueueCore core;
        std::atomic<int> ready{0};
        std::atomic<int> done{0};
        constexpr int waiters=4;
        std::promise<void> all_done;
        auto result=all_done.get_future();
        std::vector<std::thread> threads;
        for (int i=0; i<waiters; ++i) {
            threads.emplace_back([&] {
                std::unique_lock lock{core.mutex};
                ++ready;
                assert(core.WaitForDequeueCondition(lock));
                if (++done == waiters) all_done.set_value();
            });
        }
        auto deadline=std::chrono::steady_clock::now()+3s;
        while (ready.load()!=waiters && std::chrono::steady_clock::now()<deadline)
            std::this_thread::yield();
        assert(ready.load()==waiters);
        {
            std::lock_guard lock{core.mutex};
            core.SignalDequeueCondition();
        }
        assert(result.wait_for(3s)==std::future_status::ready);
        for (auto& thread:threads) thread.join();
        assert(done.load()==waiters);
    }
    std::puts("PASS: 400 guest waiters, 100 broadcast generations; render callback is non-flushing");
}
""".replace("__REAL_METHODS__", real_methods)

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-buffer-wake-") as tmp:
    src = Path(tmp) / "guest_buffer_wake.cpp"
    exe = Path(tmp) / "guest_buffer_wake"
    src.write_text(fixture)
    subprocess.run([compiler, "-std=c++20", "-O1", "-pthread",
                    "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)],
                   check=True, timeout=45)
    subprocess.run([str(exe)], check=True, timeout=35)
print("HOST ONLY: native driver integration and title regression remain untested")
