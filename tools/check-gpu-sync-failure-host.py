#!/usr/bin/env python3
"""Qualify source-derived native GPU sync waits after a fatal worker failure.

A stopped GPU worker cannot acknowledge new fences. This host-only ASan/UBSan
fixture checks that pending CPU waiters observe the recorded fatal error
without consuming it for other waiters. It performs no console build.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/video_core/gpu.cpp").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
header = (root / "headless/gpu_failure.h").read_text()
native_method = (root / "headless/gpu_sync_failure_wait.inc").read_text()
original = """    void WaitForSyncOperation(const u64 fence) {
        std::unique_lock lck{sync_request_mutex};
        sync_request_cv.wait(lck, [this, fence] { return sync_requests_stopped || CurrentSyncRequestFence() >= fence; });
    }"""
stopped_pinned = pinned.replace(
    "return CurrentSyncRequestFence() >= fence;",
    "return sync_requests_stopped || CurrentSyncRequestFence() >= fence;"
)
assert stopped_pinned.count(original) == 1
assert "file(READ \"${EDEN_PORT_DIR}/gpu_sync_failure_wait.inc\" gpu_sync_wait_replacement)" in cmake
assert 'string(FIND "${gpu_source}" "${gpu_sync_wait_original}" gpu_sync_wait_position)' in cmake
assert 'string(PREPEND gpu_source "#include \\"' not in cmake or "gpu_failure.h" in cmake
assert "std::rethrow_exception(failure);" in native_method
assert "sync_request_cv.wait_for(lck, std::chrono::milliseconds(100));" in native_method
assert "std::exception_ptr PeekGpuFailure()" in header
assert native_method.startswith("    void") is False or "WaitForSyncOperation" in native_method
derived = stopped_pinned.replace(original, native_method.rstrip("\n"))
assert derived.count("std::rethrow_exception(failure);") == 2
assert derived.count("sync_request_cv.wait_for(lck, std::chrono::milliseconds(100));") == 1

source = r"""
#include "gpu_failure.h"
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <exception>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <thread>
using u64 = std::uint64_t;
struct GPU {
    std::mutex sync_request_mutex;
    std::condition_variable sync_request_cv;
    std::atomic<u64> current_sync_fence{};
    bool sync_requests_stopped{};
    [[nodiscard]] u64 CurrentSyncRequestFence() const {
        return current_sync_fence.load(std::memory_order_relaxed);
    }
__NATIVE_METHOD__
    void Complete(u64 seq) {
        {
            std::lock_guard lock(sync_request_mutex);
            current_sync_fence.store(seq, std::memory_order_release);
        }
        sync_request_cv.notify_all();
    }
    void Stop() {
        {
            std::lock_guard lock(sync_request_mutex);
            sync_requests_stopped = true;
        }
        sync_request_cv.notify_all();
    }
};
int main() {
    assert(!Eden::TakeGpuFailure());
    GPU normal;
    std::atomic<bool> success{false};
    std::thread completed([&] {
        normal.WaitForSyncOperation(1);
        success.store(true, std::memory_order_release);
    });
    normal.Complete(1);
    completed.join();
    assert(success.load(std::memory_order_acquire));
    assert(normal.CurrentSyncRequestFence() == 1);

    // The GPU worker has failed, leaving two distinct fence requests
    // unacknowledged. Neither waiter may hang, and failure must be visible
    // to BOTH without TakeGpuFailure consuming the cause.
    GPU failed;
    std::atomic<unsigned> caught{};
    std::thread a([&] {
        try { failed.WaitForSyncOperation(2); }
        catch (const std::runtime_error&) { caught.fetch_add(1); }
    });
    std::thread b([&] {
        try { failed.WaitForSyncOperation(3); }
        catch (const std::runtime_error&) { caught.fetch_add(1); }
    });
    Eden::RecordGpuFailure(std::make_exception_ptr(
        std::runtime_error("GPU worker exited before replay")));
    a.join();
    b.join();
    assert(caught.load() == 2);
    assert(failed.CurrentSyncRequestFence() == 0);
    assert(Eden::PeekGpuFailure());
    assert(Eden::TakeGpuFailure());
    assert(!Eden::PeekGpuFailure());

    // An orderly title shutdown preserves the existing cancellation
    // semantics and must not fabricate completion for abandoned requests.
    GPU stopped;
    std::thread cancelled([&] { stopped.WaitForSyncOperation(10); });
    stopped.Stop();
    cancelled.join();
    assert(stopped.CurrentSyncRequestFence() == 0);
}
""".replace("__NATIVE_METHOD__", native_method)
with tempfile.TemporaryDirectory(prefix="encore-gpu-sync-fail-host-") as d:
    source_file = Path(d) / "test.cpp"
    executable = Path(d) / "test"
    source_file.write_text(source)
    subprocess.run([
        "clang++", "-std=c++20", "-O1", "-g", "-pthread", "-Wall",
        "-Wextra", "-Werror", "-fsanitize=address,undefined",
        "-fno-sanitize-recover=all", "-I", str(root / "headless"),
        str(source_file), "-o", str(executable)
    ], check=True, timeout=45)
    subprocess.run([str(executable)], check=True, timeout=30)
print("GPU_SYNC_WORKER_FAILURE_HOST_PASS normal=1 fatal_waiters=2 no_fake_fence=1 shutdown=1")
