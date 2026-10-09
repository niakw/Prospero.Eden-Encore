#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Host replay of native worker registration destructor and stale-ID protection.

Extracts the real WorkerRegistration C++ source; does not run a PS5 title or
prove the kernel signal-vs-teardown race is absent.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
perf = (root / "headless/performance.cpp").read_text()
begin = perf.index("struct WorkerRegistration {")
end = perf.index("thread_local WorkerRegistration owned_worker;", begin)
body = perf[begin:end + len("thread_local WorkerRegistration owned_worker;")]
assert "if (entry.registered && pthread_equal(entry.thread, owner))" in body
assert "entry.registered = false;" in body
assert "std::lock_guard lock(workers_mutex)" in body
compiler = next((name for name in ("clang++-18", "clang++", "g++") if shutil.which(name)), None)
if not compiler:
    raise SystemExit("C++20 compiler required for source-extracted worker exit test")
prefix = r"""
#include <array>
#include <cassert>
#include <future>
#include <mutex>
#include <pthread.h>
#include <thread>
#include <string_view>

namespace Eden::Performance {
namespace {
constexpr std::array names{"CPUCore_0", "CPUCore_1", "CPUCore_2", "CPUCore_3",
                           "GPU", "HostTiming", "VSyncThread"};
struct Worker { pthread_t thread{}; bool registered = false; };
std::mutex workers_mutex;
std::array<Worker, names.size()> workers;
"""
suffix = r"""
} // namespace
} // namespace Eden::Performance

int main() {
    using namespace Eden::Performance;
    // Thread exit must clear its own worker slot.
    std::thread first([] {
        owned_worker.owner = pthread_self();
        owned_worker.index = 4;
        std::lock_guard lock(workers_mutex);
        workers[4] = Worker{pthread_self(), true};
    });
    first.join();
    assert(!workers[4].registered);

    // Owner A exits after owner B has registered into the same slot.
    // A's stale TLS cleanup must not clear B's current identity.
    std::promise<void> first_ready, second_ready;
    std::promise<void> let_first_exit, let_second_exit;
    auto first_wait = let_first_exit.get_future();
    auto second_wait = let_second_exit.get_future();
    std::thread old([&] {
        owned_worker.owner = pthread_self();
        owned_worker.index = 4;
        {
            std::lock_guard lock(workers_mutex);
            workers[4] = Worker{pthread_self(), true};
        }
        first_ready.set_value();
        first_wait.wait();
    });
    first_ready.get_future().wait();
    std::thread newer([&] {
        owned_worker.owner = pthread_self();
        owned_worker.index = 4;
        {
            std::lock_guard lock(workers_mutex);
            workers[4] = Worker{pthread_self(), true};
        }
        second_ready.set_value();
        second_wait.wait();
    });
    second_ready.get_future().wait();
    let_first_exit.set_value();
    old.join();
    assert(workers[4].registered);
    let_second_exit.set_value();
    newer.join();
    assert(!workers[4].registered);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-worker-exit-") as temporary:
    folder = Path(temporary)
    src, exe = folder / "worker.cpp", folder / "worker"
    src.write_text(prefix + body + suffix)
    subprocess.run([compiler, "-std=c++20", "-O2", "-pthread", "-Wall",
                    "-Wextra", "-Werror", str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("PASS: actual worker TLS exit clears its slot, never clears a newer thread owner")
print("PS5 kernel pthread reuse/signal race and firmware build remain UNTESTED")
