#!/usr/bin/env python3
"""Compile the selected native dequeue call with the DEV timer on and off."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "vendor/encore-active/eden-core/src/core/hle/service/nvnflinger/buffer_queue_producer.cpp").read_text()
cmake = (ROOT / "headless/CMakeLists.txt").read_text()
header = (ROOT / "headless/performance.h").read_text()
report = (ROOT / "headless/performance.cpp").read_text()
profile = "EDEN_NVNF_DEQUEUE_PROFILE"
assert src.startswith('#ifdef ' + profile + '\n#include "performance.h"\n#endif\n')
assert cmake.count('list(APPEND core_sources "$' + '{EDEN_MAINTAINED_PROFILE_DEQUEUE}")') == 1
assert cmake.count("target_compile_definitions(core PRIVATE " + profile + "=1)") == 1
assert "buffer_queue_producer_standard.cpp" not in cmake
assert "::Eden::Performance::GuestDequeueBlockedScope blocking_scope;" in src
assert src.count("::Eden::Performance::GuestDequeueBlockedScope blocking_scope;") == 1
assert "dequeue_blocked=%u" in report
assert "guest_dequeue_blocked.load(std::memory_order_acquire)" in report
scope_start = "class GuestDequeueBlockedScope {"
assert header.count(scope_start) == 1
begin = header.index(scope_start)
scope = header[begin:header.index("\n};", begin)+3]
assert "guest_dequeue_blocked.fetch_add(1, std::memory_order_acq_rel)" in scope
assert "guest_dequeue_blocked.fetch_sub(1, std::memory_order_acq_rel)" in scope
assert "detailed_gpu_profile.load(std::memory_order_relaxed)" in scope
start = src.index("#ifdef " + profile + "\n        const auto dequeue_start")
end = src.index("        if (status != Status::NoError)", start)
fragment = src[start:end]
assert fragment.count("#ifdef " + profile) == 2
assert fragment.count("#endif") == 2
assert fragment.count("Status status = WaitForFreeSlotThenRelock(") == 1
assert fragment.count("::Eden::Performance::AddSince(") == 1
fixture = r"""
#include <atomic>
#include <cassert>
#include <mutex>
using s32 = int;
enum class Status { NoError, BadValue };
#ifdef EDEN_NVNF_DEQUEUE_PROFILE
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{true};
inline std::atomic<int> clock_calls{};
inline std::atomic<int> add_calls{};
constexpr int guest_dequeue_wait = 1;
long long NowNs() { ++clock_calls; return 100; }
void AddSince(int key, long long stamp) {
    assert(key == guest_dequeue_wait && stamp == 100);
    ++add_calls;
}
}
#endif
struct Probe {
    std::mutex mutex;
    int calls{};
    Status WaitForFreeSlotThenRelock(bool async, s32* found, Status* flags,
                                     std::unique_lock<std::mutex>& lock) {
        assert(lock.owns_lock() && !async && found && flags);
        ++calls;
        return Status::NoError;
    }
    Status Run() {
        bool async = false;
        s32 found = -1;
        Status return_flags = Status::NoError;
        std::unique_lock<std::mutex> lock(mutex);
""" + fragment + r"""
        return status;
    }
};
int main() {
    Probe p{};
    assert(p.Run() == Status::NoError && p.calls == 1);
#ifdef EDEN_NVNF_DEQUEUE_PROFILE
    assert(Eden::Performance::clock_calls == 1 && Eden::Performance::add_calls == 1);
    Eden::Performance::detailed_gpu_profile.store(false);
    assert(p.Run() == Status::NoError && p.calls == 2);
    assert(Eden::Performance::clock_calls == 1 && Eden::Performance::add_calls == 1);
#else
    assert(p.Run() == Status::NoError && p.calls == 2);
#endif
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-dequeue-profile-") as tmp:
    source = Path(tmp) / "selected.cpp"
    source.write_text(fixture)
    for profile_on in (False, True):
        for opt in ("-O0", "-O2"):
            binary = Path(tmp) / f"selected-{int(profile_on)}-{opt}"
            args = [compiler, "-std=c++20", opt, "-pthread", "-Wall", "-Wextra",
                    "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all"]
            if profile_on:
                args.append("-DEDEN_NVNF_DEQUEUE_PROFILE=1")
            subprocess.run([*args, str(source), "-o", str(binary)], check=True, timeout=45)
            subprocess.run([str(binary)], check=True, timeout=12)
            print("NATIVE_NVN_DEQUEUE_PROFILE_PASS", "dev" if profile_on else "release", opt)


# Native source-extracted scope: multiple host dequeuers, early scope exit
# and disabled-profile path must never leak a nonzero active-blocker counter.
active_scope_fixture = r"""
#include <atomic>
#include <cassert>
#include <thread>
#include <vector>
#include <cstdio>
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{true};
inline std::atomic<unsigned> guest_dequeue_blocked{};
__SCOPE__
}
int main() {
    using namespace Eden::Performance;
    {
        GuestDequeueBlockedScope first{};
        assert(guest_dequeue_blocked.load() == 1);
        { GuestDequeueBlockedScope second{}; assert(guest_dequeue_blocked.load() == 2); }
        assert(guest_dequeue_blocked.load() == 1);
    }
    assert(guest_dequeue_blocked.load() == 0);
    std::atomic<unsigned> entered{};
    std::atomic<bool> release{};
    std::vector<std::thread> workers;
    for (int n = 0; n < 8; ++n) {
        workers.emplace_back([&] {
            GuestDequeueBlockedScope active{};
            entered.fetch_add(1, std::memory_order_release);
            while (!release.load(std::memory_order_acquire)) std::this_thread::yield();
        });
    }
    while (entered.load(std::memory_order_acquire) != 8) std::this_thread::yield();
    assert(guest_dequeue_blocked.load(std::memory_order_acquire) == 8);
    release.store(true, std::memory_order_release);
    for (auto& worker : workers) worker.join();
    assert(guest_dequeue_blocked.load(std::memory_order_acquire) == 0);
    detailed_gpu_profile.store(false);
    { GuestDequeueBlockedScope quiet{}; assert(guest_dequeue_blocked.load() == 0); }
    assert(guest_dequeue_blocked.load() == 0);
    std::puts("F05_ACTIVE_DEQUEUE_BLOCKERS_PASS blocked=8 cleared=1 disabled_quiet=1 scope=source_extracted");
}
""".replace("__SCOPE__", scope)
with tempfile.TemporaryDirectory(prefix="encore-f05-live-dequeue-") as tmp:
    source = Path(tmp) / "live.cpp"
    source.write_text(active_scope_fixture)
    for opt in ("-O0", "-O2"):
        exe = Path(tmp) / ("live" + opt)
        compiled = subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra",
                                   "-Werror", "-pthread", "-fsanitize=undefined",
                                   "-fno-sanitize-recover=all",
                                   str(source), "-o", str(exe)],
                                  capture_output=True, text=True, timeout=45)
        assert compiled.returncode == 0, (opt, compiled.stderr[-6000:])
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
        assert run.returncode == 0, (opt, run.stderr[-6000:], run.stdout)
        assert "F05_ACTIVE_DEQUEUE_BLOCKERS_PASS blocked=8 cleared=1 disabled_quiet=1" in run.stdout
        print(opt, run.stdout.strip(), flush=True)
print("F05_LIVE_DEQUEUE_DIAGNOSTIC_NOT_GUEST_PC_OR_FC27_LIVENESS_PROOF")


# F05 integration: the *actual selected* blocking branch and the maintained
# BufferQueueCore epoch/condition methods must agree with the active counter.
# Merely testing an isolated RAII object cannot prove this runtime boundary.
core_source = (
    ROOT / "vendor/encore-active/eden-backports/src/core/hle/service/nvnflinger/buffer_queue_core.cpp"
).read_text()
core_begin = "void BufferQueueCore::SignalDequeueCondition() {"
core_end = "\ns32 BufferQueueCore::GetMinUndequeuedBufferCountLocked("
assert core_source.count(core_begin) == 1 and core_source.count(core_end) == 1
core_methods = core_source[
    core_source.index(core_begin):core_source.index(core_end, core_source.index(core_begin))
]
assert "dequeue_condition.notify_all();" in core_methods
assert "dequeue_condition.wait(lk," in core_methods
block_begin = "#ifdef EDEN_NVNF_DEQUEUE_PROFILE\n            // F05: a producer stuck inside this wait"
block_end = (
    "            if (!core->WaitForDequeueCondition(lk)) {\n"
    "                // We are no longer running\n"
    "                return Status::NoError;\n"
    "            }\n"
)
assert src.count(block_begin) == 1 and src.count(block_end) == 1
block_at = src.index(block_begin)
block_end_at = src.index(block_end, block_at) + len(block_end)
block_path = src[block_at:block_end_at]
assert block_path.count("GuestDequeueBlockedScope blocking_scope;") == 1
assert block_path.count("WaitForDequeueCondition(lk)") == 1

condition_fixture = r"""
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <thread>
#include <vector>
namespace Eden::Performance {
inline std::atomic<bool> detailed_gpu_profile{true};
inline std::atomic<unsigned> guest_dequeue_blocked{};
__SCOPE__
}
enum class Status { NoError };
struct BufferQueueCore {
    std::mutex mutex{};
    std::atomic<unsigned> dequeue_epoch{};
    std::condition_variable dequeue_condition{};
    void SignalDequeueCondition();
    bool WaitForDequeueCondition(std::unique_lock<std::mutex>&);
};
__CORE_METHODS__
struct Producer {
    BufferQueueCore* core;
    Status BlockOnce(std::atomic<int>& entered) {
        std::unique_lock lk{core->mutex};
        entered.fetch_add(1, std::memory_order_release);
__BLOCK_PATH__
        return Status::NoError;
    }
};
int main() {
    using namespace Eden::Performance;
    BufferQueueCore core{};
    Producer producer{&core};
    std::atomic<int> entered{};
    std::vector<std::thread> waiters;
    for (int i = 0; i < 8; ++i) {
        waiters.emplace_back([&] { assert(producer.BlockOnce(entered) == Status::NoError); });
    }
    while (entered.load(std::memory_order_acquire) != 8)
        std::this_thread::yield();
    {
        // Owning this mutex proves that every prior waiter entered the
        // native condvar wait (and released the mutex) before broadcasting.
        std::scoped_lock lock{core.mutex};
#ifdef EDEN_NVNF_DEQUEUE_PROFILE
        assert(guest_dequeue_blocked.load(std::memory_order_acquire) == 8);
#else
        assert(guest_dequeue_blocked.load(std::memory_order_acquire) == 0);
#endif
        core.SignalDequeueCondition();
    }
    for (auto& waiter : waiters) waiter.join();
    assert(guest_dequeue_blocked.load(std::memory_order_acquire) == 0);
    assert(core.dequeue_epoch.load(std::memory_order_relaxed) == 1);
#ifdef EDEN_NVNF_DEQUEUE_PROFILE
    detailed_gpu_profile.store(false);
    entered.store(0);
    std::thread quiet([&] { assert(producer.BlockOnce(entered) == Status::NoError); });
    while (entered.load(std::memory_order_acquire) != 1)
        std::this_thread::yield();
    {
        std::scoped_lock lock{core.mutex};
        assert(guest_dequeue_blocked.load(std::memory_order_acquire) == 0);
        core.SignalDequeueCondition();
    }
    quiet.join();
    assert(guest_dequeue_blocked.load() == 0);
#endif
    std::puts("F05_NATIVE_DEQUEUE_CONDITION_INFLIGHT_PASS waiters=8 "
              "active_gauge_correct=1 restored=1 disabled_quiet=1 "
              "scope=source_extracted_native_condvar");
}
""".replace("__SCOPE__", scope).replace(
    "__CORE_METHODS__", core_methods).replace("__BLOCK_PATH__", block_path)

with tempfile.TemporaryDirectory(prefix="encore-f05-condvar-live-") as tmp:
    source = Path(tmp) / "native-condvar.cpp"
    source.write_text(condition_fixture)
    for profile_on in (False, True):
        for mode in ("-O0", "-O2"):
            binary = Path(tmp) / f"condition-{int(profile_on)}-{mode}"
            command = [
                compiler, "-std=c++20", mode, "-Wall", "-Wextra", "-Werror",
                "-pthread", "-fsanitize=undefined", "-fno-sanitize-recover=all",
            ]
            if profile_on:
                command.append("-DEDEN_NVNF_DEQUEUE_PROFILE=1")
            result = subprocess.run(
                [*command, str(source), "-o", str(binary)],
                capture_output=True, text=True, timeout=90,
            )
            assert result.returncode == 0, (mode, profile_on, result.stderr[-7000:])
            run = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=25,
            )
            assert run.returncode == 0, (mode, profile_on, run.stderr[-7000:])
            assert run.stdout.count("F05_NATIVE_DEQUEUE_CONDITION_INFLIGHT_PASS") == 1
            print("profile=" + str(int(profile_on)), mode, run.stdout.strip(), flush=True)
print("F05_CONDITION_WAITER_HOST_ONLY_NOT_GUEST_IPC_OR_FC27_PROGRESS")
