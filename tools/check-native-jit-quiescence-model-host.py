#!/usr/bin/env python3
"""Source-anchored, host-only JIT run-quiescence model; never enables native bridge."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
def read(path):
    return (root / path).read_text()

physical = read("vendor/sources/eden/src/core/hle/kernel/physical_core.cpp")
cpu = read("vendor/sources/eden/src/core/cpu_manager.cpp")
kernel = read("vendor/sources/eden/src/core/hle/kernel/kernel.cpp")
gpu = read("vendor/sources/eden/src/video_core/gpu.cpp")
a32 = read("vendor/sources/eden/src/core/arm/dynarmic/arm_dynarmic_32.cpp")
a64 = read("vendor/sources/eden/src/core/arm/dynarmic/arm_dynarmic_64.cpp")
replay = read("headless/gpu_deferred_replay.h")
workflow = read(".github/workflows/encore-core-preflight.yml")
for anchor in ("const auto EnterContext = [&]() {", "const auto ExitContext = [&]() {",
               "interface->RunThread(thread);", "interface->UnlockThread(thread);",
               "arm_interface->SignalInterrupt(thread);"):
    assert anchor in physical, anchor
assert "while (!physical_core->IsInterrupted())" in cpu
assert "while (!TryWait())" in kernel
assert "WaitForSyncOperation(fence);" in gpu
for jit in (a32, a64):
    assert "m_jit->HaltExecution(BreakLoop);" in jit
assert "inline constexpr bool kNativePostStorePublicationReady = false;" in replay
assert "python3 -B tools/check-native-jit-quiescence-model-host.py" in workflow

code = r"""
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <semaphore>
#include <thread>
struct Gate {
    std::mutex m;
    std::condition_variable cv;
    unsigned in_flight = 0;
    bool pending = false, tracked = false, failed = false;
    std::atomic<bool> direct{true};
    std::atomic<int> ram{0};
    std::atomic<unsigned> callbacks{0};
    bool enter() {
        std::unique_lock lk(m);
        cv.wait(lk, [&] { return !pending || failed; });
        if (failed) return false;
        ++in_flight;
        return true;
    }
    void exit() {
        std::lock_guard lk(m);
        assert(in_flight > 0);
        --in_flight;
        cv.notify_all();
    }
    void request() {
        std::lock_guard lk(m);
        assert(!pending && !tracked && !failed);
        pending = true;
        direct.store(false, std::memory_order_release);
    }
    bool confirm() {
        std::lock_guard lk(m);
        if (!pending || in_flight || failed) return false;
        tracked = true;
        pending = false;
        cv.notify_all();
        return true;
    }
    void abort() {
        std::lock_guard lk(m);
        failed = true;
        pending = false;
        cv.notify_all();
    }
};
void exercise_gpu_wait_and_first_use() {
    Gate gate;
    std::binary_semaphore old_guard_read{0}, finish_old_store{0};
    std::binary_semaphore waiting_for_gpu{0}, complete_gpu_read{0};
    std::atomic<bool> new_run_started{false};
    std::thread writer([&] {
        assert(gate.enter());
        bool already_allowed = gate.direct.load(std::memory_order_acquire);
        assert(already_allowed);
        old_guard_read.release();
        finish_old_store.acquire();
        if (already_allowed) gate.ram.store(17, std::memory_order_release);
        gate.exit();
    });
    std::thread gpu_waiter([&] {
        assert(gate.enter());
        waiting_for_gpu.release();
        complete_gpu_read.acquire();
        gate.exit();
    });
    old_guard_read.acquire();
    waiting_for_gpu.acquire();
    gate.request();
    assert(!gate.confirm());
    std::thread newcomer([&] {
        assert(gate.enter());
        new_run_started.store(true, std::memory_order_release);
        if (gate.direct.load(std::memory_order_acquire))
            gate.ram.store(99, std::memory_order_release);
        else
            gate.callbacks.fetch_add(1, std::memory_order_relaxed);
        gate.exit();
    });
    assert(!new_run_started.load(std::memory_order_acquire));
    // The GPU owner keeps servicing guest requests instead of waiting.
    complete_gpu_read.release();
    finish_old_store.release();
    gpu_waiter.join();
    writer.join();
    assert(gate.confirm());
    newcomer.join();
    assert(new_run_started && gate.tracked && gate.ram == 17);
    assert(gate.callbacks == 1);
    std::puts("JIT_QUIESCENCE_GPU_PROGRESS_AND_FIRST_USE_MODEL_PASS");
}
void exercise_reentrant_guest_request() {
    Gate gate;
    assert(gate.enter());
    gate.request();
    assert(!gate.confirm()); // Waiting here would deadlock on this very RUN.
    gate.ram.store(19);
    gate.exit();
    assert(gate.confirm() && gate.ram == 19);
    std::puts("JIT_QUIESCENCE_REENTRANT_NONBLOCKING_MODEL_PASS");
}
void exercise_abort() {
    Gate gate;
    assert(gate.enter());
    gate.request();
    gate.abort();
    gate.exit();
    assert(!gate.confirm() && !gate.enter());
    std::puts("JIT_QUIESCENCE_FAILURE_FAIL_CLOSED_MODEL_PASS");
}
int main() {
    exercise_gpu_wait_and_first_use();
    exercise_reentrant_guest_request();
    exercise_abort();
    std::puts("JIT_QUIESCENCE_NATIVE_UNQUALIFIED_GATE_CLOSED");
}
"""
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler, "C++20 host compiler required"
with tempfile.TemporaryDirectory(prefix="encore-jit-quiescence-") as folder:
    source = Path(folder) / "model.cpp"
    executable = Path(folder) / "model"
    source.write_text(code)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra",
                    "-Werror", "-pthread", str(source), "-o", str(executable)],
                   check=True)
    completed = subprocess.run([str(executable)], text=True, capture_output=True,
                               check=True, timeout=15)
    print(completed.stdout, end="")
