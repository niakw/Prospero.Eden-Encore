#!/usr/bin/env python3
"""Compile Eden's actual BufferQueueCore wake/wait methods; prove broadcast wakeups."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (Path(sys.argv[1]) if len(sys.argv) > 1 else
          root / 'vendor/encore-active/eden-backports')
header = (source / 'src/core/hle/service/nvnflinger/buffer_queue_core.h').read_text()
cpp = (source / 'src/core/hle/service/nvnflinger/buffer_queue_core.cpp').read_text()
assert 'std::atomic<std::uint64_t> dequeue_epoch{};' in header
assert 'dequeue_possible' not in header + cpp
begin = cpp.index('void BufferQueueCore::SignalDequeueCondition() {')
end = cpp.index('s32 BufferQueueCore::GetMinUndequeuedBufferCountLocked(', begin)
methods = cpp[begin:end]
assert 'dequeue_epoch.fetch_add(1, std::memory_order_relaxed)' in methods
assert 'dequeue_condition.notify_all()' in methods
assert 'dequeue_condition.wait(lk,' in methods

head = r'''#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <thread>
class BufferQueueCore {
public:
    void SignalDequeueCondition();
    bool WaitForDequeueCondition(std::unique_lock<std::mutex>& lk);
    std::mutex mutex;
    std::condition_variable dequeue_condition;
    std::atomic<std::uint64_t> dequeue_epoch{};
};
'''
tail = r'''int main() {
    using namespace std::chrono_literals;
    for (int round = 0; round < 100; ++round) {
        BufferQueueCore core;
        std::atomic<int> entered{0};
        std::atomic<int> woken{0};
        auto waiter = [&]() {
            std::unique_lock lk(core.mutex);
            entered.fetch_add(1);
            if (core.WaitForDequeueCondition(lk)) woken.fetch_add(1);
        };
        std::thread a(waiter), b(waiter);
        while (entered.load() < 2) std::this_thread::yield();
        // Both threads have entered wait() before we acquire this mutex.
        { std::unique_lock lk(core.mutex); }
        core.SignalDequeueCondition();
        const auto deadline = std::chrono::steady_clock::now() + 100ms;
        while (woken.load() < 2 && std::chrono::steady_clock::now() < deadline)
            std::this_thread::sleep_for(100us);
        const bool broadcast = woken.load() == 2;
        // Recover after failure rather than hanging the negative-control run.
        if (!broadcast) { core.SignalDequeueCondition(); core.SignalDequeueCondition(); }
        a.join(); b.join();
        if (!broadcast) { std::fprintf(stderr,"Lost broadcast wakeup at round %d\n",round); return 2; }
    }
    std::puts("Actual Eden BufferQueueCore signal/wait: 100 two-producer broadcasts PASS");
}
'''
with tempfile.TemporaryDirectory(prefix='eden-dequeue-test-') as tmp:
    path = Path(tmp)
    (path / 'test.cpp').write_text(head + methods + tail)
    binary = path / 'test'
    env = os.environ.copy()
    if sys.platform == 'darwin' and not env.get('SDKROOT'):
        # Some CLT installations default to a newer .tbd format than their linker can read.
        for name in ('MacOSX15.4.sdk', 'MacOSX15.sdk'):
            candidate = Path('/Library/Developer/CommandLineTools/SDKs') / name
            if candidate.is_dir():
                env['SDKROOT'] = str(candidate)
                break
    subprocess.run(['c++', '-std=c++20', '-O1', '-pthread', '-Wall', '-Wextra',
                    str(path / 'test.cpp'), '-o', str(binary)], check=True, env=env)
    subprocess.run([str(binary)], check=True, timeout=15)
