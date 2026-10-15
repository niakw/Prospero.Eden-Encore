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
assert "std::rethrow_exception(failure);" in native_method
assert "sync_request_cv.wait_for(lck, std::chrono::milliseconds(100));" in native_method
assert "std::exception_ptr PeekGpuFailure()" in header
assert "void WaitForSyncOperation(const u64 fence)" in native_method
assert '#include \\"' not in native_method
derived = stopped_pinned.replace(original, native_method.rstrip("\n"))
assert derived.count("std::rethrow_exception(failure);") == 2
assert derived.count("sync_request_cv.wait_for(lck, std::chrono::milliseconds(100));") == 1
# Follow the EXACT native CMake derivation fragment, not a handwritten
# approximation. The shipped build uses --graphics and compiles this GPU path
# even when the selected renderer backend is Vulkan.
assert '-DEDEN_PS5_OPENGL="$graphics"' in (root / "tools/build-headless-native.sh").read_text()
assert 'tools/build-headless-native.sh --graphics' in (root / "tools/build-package.sh").read_text()
start = cmake.index("    set(gpu_sync_wait_original [=[")
end = cmake.index('    string(REPLACE "GPU::~GPU() = default;"', start)
fragment = cmake[start:end]
with tempfile.TemporaryDirectory(prefix="encore-gpu-sync-derive-") as d:
    directory = Path(d)
    outfile = directory / "native_gpu.cpp"
    cmakefile = directory / "derive.cmake"
    cmakefile.write_text(
        'cmake_minimum_required(VERSION 3.25)\n'
        + f'set(EDEN_PORT_DIR "{(root / "headless").as_posix()}")\n'
        + f'file(READ "{(root / "vendor/sources/eden/src/video_core/gpu.cpp").as_posix()}" gpu_source)\n'
        + 'string(REPLACE "return CurrentSyncRequestFence() >= fence;" '
        + '"return sync_requests_stopped || CurrentSyncRequestFence() >= fence;" '
        + 'gpu_source "${gpu_source}")\n'
        + fragment + '\n'
        + f'file(WRITE "{outfile.as_posix()}" "${{gpu_source}}")\n'
    )
    subprocess.run(["cmake", "-P", str(cmakefile)], check=True, timeout=20)
    generated = outfile.read_text()
    assert native_method.rstrip("\n") in generated
    assert generated.count("std::rethrow_exception(failure);") == 2
    tick_method = "    void TickWork() {" + generated.split("    void TickWork() {", 1)[1].split(
        "    [[nodiscard]] u64 GetTicks() const", 1)[0]
    assert "lck.unlock();" in tick_method and "lck.lock();" in tick_method
    assert "for (auto remaining = sync_requests.size(); remaining != 0; --remaining)" in tick_method
    assert "while (!sync_requests.empty())" not in tick_method
    assert "sync_request_mutex.unlock();" not in tick_method
    assert tick_method.index("lck.unlock();") < tick_method.index("request();")
    assert tick_method.index("request();") < tick_method.index("lck.lock();")
    assert "#include \"" + (root / "headless/gpu_failure.h").as_posix() + "\"" in generated

source = r"""
#include "gpu_failure.h"
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <exception>
#include <functional>
#include <list>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>
using u64 = std::uint64_t;
struct GPU {
    std::mutex sync_request_mutex;
    std::condition_variable sync_request_cv;
    std::list<std::function<void()>> sync_requests;
    std::atomic<u64> current_sync_fence{};
    bool sync_requests_stopped{};
    [[nodiscard]] u64 CurrentSyncRequestFence() const {
        return current_sync_fence.load(std::memory_order_relaxed);
    }
__NATIVE_METHOD__
__NATIVE_TICK_METHOD__
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
    {
        std::lock_guard lock(normal.sync_request_mutex);
        normal.sync_requests.emplace_back([]{});
    }
    normal.TickWork();
    completed.join();
    assert(success.load(std::memory_order_acquire));
    assert(normal.CurrentSyncRequestFence() == 1);

    // An exception inside a GPU callback must unwind the queue's
    // unique_lock without double-unlocking the raw mutex.
    GPU throwing;
    throwing.sync_requests.emplace_back([] {
        throw std::runtime_error("rasterizer callback failed");
    });
    bool caught_callback = false;
    try { throwing.TickWork(); }
    catch (const std::runtime_error&) { caught_callback = true; }
    assert(caught_callback);
    assert(throwing.CurrentSyncRequestFence() == 0);
    {
        std::unique_lock lock(throwing.sync_request_mutex, std::try_to_lock);
        assert(lock.owns_lock());
    }

    // Reentrant sync work is not allowed to starve the GPU command owner:
    // only callbacks queued at tick entry may run in this invocation.
    // Every later callback needs the next already-scheduled GPU tick.
    GPU bounded;
    unsigned callbacks = 0;
    std::function<void()> refill;
    refill = [&] {
        ++callbacks;
        if (callbacks < 16) {
            std::lock_guard lock(bounded.sync_request_mutex);
            bounded.sync_requests.emplace_back(refill);
        }
    };
    {
        std::lock_guard lock(bounded.sync_request_mutex);
        bounded.sync_requests.emplace_back(refill);
    }
    for (unsigned tick = 1; tick <= 16; ++tick) {
        bounded.TickWork();
        assert(callbacks == tick);
        assert(bounded.CurrentSyncRequestFence() == tick);
        std::lock_guard lock(bounded.sync_request_mutex);
        assert(bounded.sync_requests.size() == (tick < 16 ? 1u : 0u));
    }

    // A batch with two initial requests preserves both completions and
    // postpones reentrant work, maintaining global FIFO fence order.
    GPU two_initial;
    std::vector<unsigned> completion_order;
    {
        std::lock_guard lock(two_initial.sync_request_mutex);
        two_initial.sync_requests.emplace_back([&] {
            completion_order.push_back(1);
            std::lock_guard enqueue_lock(two_initial.sync_request_mutex);
            two_initial.sync_requests.emplace_back([&] { completion_order.push_back(3); });
        });
        two_initial.sync_requests.emplace_back([&] { completion_order.push_back(2); });
    }
    two_initial.TickWork();
    assert((completion_order == std::vector<unsigned>{1, 2}));
    assert(two_initial.CurrentSyncRequestFence() == 2);
    two_initial.TickWork();
    assert((completion_order == std::vector<unsigned>{1, 2, 3}));
    assert(two_initial.CurrentSyncRequestFence() == 3);

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
""".replace("__NATIVE_METHOD__", native_method).replace("__NATIVE_TICK_METHOD__", tick_method)
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
print("GPU_SYNC_WORKER_FAILURE_HOST_PASS normal=1 fatal_waiters=2 no_fake_fence=1 shutdown=1 throw_lock=1")
print("GPU_TICK_SNAPSHOT_HOST_PASS reentrant=16 fifo=3 callbacks=ordered no_fake_fence=1")
