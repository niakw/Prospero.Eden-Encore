#!/usr/bin/env python3
"""Source-extracted GPU queue producer stop-aware fast path witness.

The maintained SPSCQueue has a single producer (protected by the parent GPU
thread manager). Verify slot reuse, already-freed fast case, full-queue wake
and stop request while full. Never infer improved console frame timings.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "vendor/encore-active/eden-gpu/include/common/bounded_threadsafe_queue.h").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
producer = header.split("bool EmplaceWaitWithStopToken(", 1)[1].split("\n\n    bool TryPop(", 1)[0]
assert "python3 -B tools/check-native-gpu-queue-stop-fastpath-host.py" in workflow
early = "if ((write_index - consumer.index.load(std::memory_order_acquire)) >= Capacity)"
assert producer.count(early) == 1
assert producer.index(early) < producer.index("std::unique_lock lock{producer.cv_mutex};")
assert producer.index("if (stop_token.stop_requested()) return false;") < producer.index("const std::size_t pos")
assert "producer.cv.wait(lock, stop_token" in producer
assert producer.count("std::destroy_at(std::addressof(m_data[pos]));") == 1
assert producer.count("std::construct_at(std::addressof(m_data[pos])") == 1

cpp = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdio>
#include <memory>
#include <stop_token>
#include <thread>
#include <utility>
#include "common/bounded_threadsafe_queue.h"
int main() {
    using namespace std::chrono_literals;
    {
        Common::SPSCQueue<int, 2> q;
        std::stop_source stop;
        int value = 0;
        assert(q.TryEmplace(10) && q.TryEmplace(20));
        assert(!q.TryEmplace(30));
        assert(q.TryPop(value) && value == 10);
        // The consumer just released a slot; this must never wait.
        assert(q.EmplaceWaitWithStopToken(stop.get_token(), 30));
        assert(q.TryPop(value) && value == 20);
        assert(q.TryPop(value) && value == 30);
        assert(!q.TryPop(value));
    }
    {
        Common::SPSCQueue<int, 2> q;
        std::stop_source stop;
        assert(q.TryEmplace(1) && q.TryEmplace(2));
        std::atomic<bool> running{false}, result{true};
        std::thread producer([&] {
            running.store(true, std::memory_order_release);
            result.store(q.EmplaceWaitWithStopToken(stop.get_token(), 3));
        });
        while (!running.load(std::memory_order_acquire))
            std::this_thread::yield();
        stop.request_stop();
        producer.join();
        assert(!result.load());
        int value = 0;
        assert(q.TryPop(value) && value == 1);
        assert(q.TryPop(value) && value == 2);
        assert(!q.TryPop(value));
    }
    {
        Common::SPSCQueue<int, 2> q;
        std::stop_source stop;
        assert(q.TryEmplace(11) && q.TryEmplace(12));
        std::atomic<bool> running{false}, result{false};
        std::thread producer([&] {
            running.store(true, std::memory_order_release);
            result.store(q.EmplaceWaitWithStopToken(stop.get_token(), 13));
        });
        while (!running.load(std::memory_order_acquire))
            std::this_thread::yield();
        int value = 0;
        assert(q.TryPop(value) && value == 11);
        producer.join();
        assert(result.load());
        assert(q.TryPop(value) && value == 12);
        assert(q.TryPop(value) && value == 13);
        assert(!q.TryPop(value));
    }
    {
        Common::SPSCQueue<int, 2> q;
        std::stop_source stop;
        stop.request_stop();
        assert(!q.EmplaceWaitWithStopToken(stop.get_token(), 100));
        int value = 0;
        assert(!q.TryPop(value));
    }
    std::puts("ENCORE_GPU_QUEUE_STOP_FASTPATH_PASS");
}
"""
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-gpu-spsc-") as tmp:
    root_tmp = Path(tmp)
    common = root_tmp / "common"
    common.mkdir()
    (common / "polyfill_thread.h").write_text("#pragma once\n#include <stop_token>\n")
    # Copy real maintained source. The two portability prerequisites above
    # are also included by the full production translation unit.
    (common / "bounded_threadsafe_queue.h").write_text(header)
    src = root_tmp / "queue.cpp"
    exe = root_tmp / "queue"
    src.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O1", "-pthread", "-Wall", "-Wextra",
                    "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-I", str(root_tmp),
                    str(src), "-o", str(exe)],
                   check=True, capture_output=True, text=True, timeout=90)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, (result.stdout[-1000:], result.stderr[-2500:])
print("NATIVE_GPU_QUEUE_STOP_FASTPATH_HOST_PASS source=active empty_fastpath=1 full_wait=1 cancelled=1 asan_ubsan=1")
