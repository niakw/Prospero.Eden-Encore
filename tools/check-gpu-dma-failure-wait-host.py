#!/usr/bin/env python3
"""Exercise the actual DMA producer-side guest fence wait under host sanitizers.

A failed native GPU worker must abort a stuck DMA sync wait without forging
synced=true. Shipping/DEV and native/host variants preserve guest behavior.
This is a host protocol test, not PS5 performance evidence.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "vendor/encore-active/eden-core/src/video_core"
QUIET = (ACTIVE / "dma_pusher.cpp").read_text()
DEV = (ACTIVE / "dma_pusher_dev.cpp").read_text()
PARITY = (ROOT / "tools/check-maintained-guest-gpu-sync.py").read_text()
CI = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()

assert "DMA_FAULT_WAIT" in PARITY and "DMA_FAULT_INC" in PARITY
assert "python3 -B tools/check-gpu-dma-failure-wait-host.py" in CI
START = "    if (signal_sync && !synced) {"
END = "\n    if (header.size > 0)"
def extract(src: str) -> str:
    assert src.count(START) == 1 and src.count(END) == 1
    snippet = src[src.index(START):src.index(END)]
    assert snippet.count("::Eden::PeekGpuFailure()") == 2
    assert snippet.count("std::rethrow_exception(failure);") == 2
    assert snippet.count("#ifdef PS5_NATIVE") == 2
    assert snippet.count("sync_cv.wait_for(lk, std::chrono::milliseconds(10))") == 1
    assert "synced = false;" in snippet
    assert snippet.index("::Eden::PeekGpuFailure()") < snippet.index("sync_cv.wait_for")
    assert snippet.index("if (system.IsShuttingDown()) return false;") > snippet.rindex("::Eden::PeekGpuFailure()")
    assert src.count('#include "gpu_failure.h"') == 1
    return snippet
quiet_wait = extract(QUIET)
dev_wait = extract(DEV)
assert "DiagnosticActiveTimer" not in quiet_wait
assert dev_wait.count("DiagnosticActiveTimer") == 1

CPP = r"""
#include "gpu_failure.h"
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <mutex>
#include <stdexcept>
#include <thread>
namespace Eden::Performance {
inline int gpu_dma_sync_wait = 0;
inline int gpu_dma_sync_active_since_ns = 0;
struct DiagnosticActiveTimer {
    DiagnosticActiveTimer(int, int, bool) {}
};
}
struct System {
    std::atomic<bool> shutting_down{false};
    bool IsShuttingDown() const { return shutting_down.load(); }
};
struct Dma {
    System system;
    std::mutex sync_mutex;
    std::condition_variable sync_cv;
    bool signal_sync=true, synced=false;
    std::atomic<unsigned> acknowledges{0};
    bool Go() {
INJECT
        ++acknowledges;
        return true;
    }
    void Satisfy() {
        std::lock_guard lock{sync_mutex};
        synced = true;
        sync_cv.notify_all();
    }
};
int main() {
    using namespace std::chrono_literals;
    Eden::ResetGpuFailureForTitle();
    {
        Dma d;
        d.Satisfy();
        assert(d.Go() && d.acknowledges==1);
        assert(d.signal_sync && d.synced);
    }
    {
        Dma d;
        std::thread waiter([&] {
            std::this_thread::sleep_for(20ms);
            d.Satisfy();
        });
        assert(d.Go() && d.acknowledges==1 && !d.signal_sync && !d.synced);
        waiter.join();
    }
    {
        Dma d;
        std::thread waiter([&] {
            std::this_thread::sleep_for(20ms);
            d.system.shutting_down = true;
            d.sync_cv.notify_all();
        });
        assert(!d.Go() && d.acknowledges==0 && d.signal_sync);
        waiter.join();
    }
#if defined(PS5_NATIVE)
    {
        Dma d;
        Eden::RecordGpuFailure(std::make_exception_ptr(std::runtime_error("fatal GPU")));
        bool caught=false;
        try { d.Go(); } catch (const std::runtime_error&) { caught=true; }
        assert(caught && !d.synced && d.signal_sync && d.acknowledges==0);
    }
    Eden::ResetGpuFailureForTitle();
    {
        Dma d;
        std::thread failure([&] {
            std::this_thread::sleep_for(24ms);
            Eden::RecordGpuFailure(std::make_exception_ptr(std::runtime_error("GPU exited")));
            d.sync_cv.notify_all();
        });
        bool caught=false;
        try { d.Go(); } catch (const std::runtime_error&) { caught=true; }
        failure.join();
        assert(caught && !d.synced && d.signal_sync && d.acknowledges==0);
        assert(Eden::PeekGpuFailure());
        (void)Eden::TakeGpuFailure();
        assert(Eden::PeekGpuFailure());
    }
    Eden::ResetGpuFailureForTitle();
    {
        Dma d;
        d.Satisfy();
        Eden::RecordGpuFailure(std::make_exception_ptr(std::runtime_error("GPU failed")));
        bool caught=false;
        try { d.Go(); } catch (const std::runtime_error&) { caught=true; }
        assert(caught && d.synced && d.acknowledges==0);
    }
    Eden::ResetGpuFailureForTitle();
#endif
}
""";
const compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-gpu-dma-failed-fence-") as tmp:
    p = Path(tmp)
    for label, snippet in (("quiet", quiet_wait), ("dev", dev_wait)):
        source = p / (label + ".cpp")
        source.write_text(CPP.replace("INJECT", snippet))
        for target_name, flags in (("host", []), ("native", ["-DPS5_NATIVE=1"])):
            exe = p / (label + "-" + target_name)
            subprocess.run(
                [compiler, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror",
                 "-pthread", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                 "-I", str(ROOT / "headless"), *flags, str(source), "-o", str(exe)],
                check=True, capture_output=True, text=True, timeout=75)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, (label, target_name, result.stdout[-900:], result.stderr[-1800:])
print("ENCORE_GPU_DMA_FATAL_WAIT_PASS actual_source=1 variants=4 native_failure=1 shutdown=1 signaled=1 asan_ubsan=1")
