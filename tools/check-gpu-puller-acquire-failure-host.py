#!/usr/bin/env python3
"""Compile source-extracted PS5 GPU semaphore acquire waits with ASan/UBSan.

A fatal GPU worker must interrupt a stuck poll without inventing a
semaphore completion. A normal acquire, shutdown, and the host variant
must still preserve their existing guest semantics.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "vendor/encore-active/eden-core/src/video_core/engines"
QUIET = (BASE / "puller.cpp").read_text()
DEV = (BASE / "puller_dev.cpp").read_text()
PARITY = (ROOT / "tools/check-maintained-guest-gpu-sync.py").read_text()
CMAKE = (ROOT / "headless/CMakeLists.txt").read_text()
WORKFLOW = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-gpu-puller-acquire-failure-host.py" in WORKFLOW
assert 'engines/puller_dev.cpp' in CMAKE and 'engines/puller.cpp' in CMAKE
assert "GPU_FAULT_LOOP" in PARITY and "GPU_FAULT_INIT" in PARITY

def method(source):
    start = source.index("void Puller::ProcessSemaphoreAcquire(DmaPusher& dma_pusher) {")
    end = source.index("\n/// Calls a GPU puller method.", start)
    extracted = source[start:end]
    assert extracted.count("::Eden::PeekGpuFailure()") == 1
    assert extracted.count("std::rethrow_exception(failure);") == 1
    assert extracted.count("dma_pusher.rasterizer->ReleaseFences();") == 1
    assert "(acquire_polls++ & 63u) == 0u" in extracted
    assert extracted.index("::Eden::PeekGpuFailure()") < extracted.index(
        "dma_pusher.rasterizer->ReleaseFences();")
    assert source.count('#include "gpu_failure.h"') == 1
    assert extracted.count("#ifdef PS5_NATIVE") == 2
    return extracted

for s in (QUIET, DEV):
    method(s)

PROGRAM = r"""
#include "gpu_failure.h"
#include <atomic>
#include <cassert>
#include <cstdint>
#include <exception>
#include <stdexcept>
using u32 = std::uint32_t;
namespace Eden::Performance {
inline int gpu_puller_semaphore_wait = 0;
inline int gpu_puller_semaphore_active_since_ns = 0;
struct DiagnosticActiveTimer {
    DiagnosticActiveTimer(int, int, bool) {}
};
}
struct Memory {
    u32 word = 0;
    unsigned reads = 0;
    template<class T> T Read(std::uint64_t) {
        ++reads;
        return static_cast<T>(word);
    }
};
struct System {
    bool shutting_down = false;
    bool IsShuttingDown() { return shutting_down; }
};
struct Rasterizer {
    Memory* memory;
    System* system;
    unsigned calls = 0;
    unsigned fulfill_after = 0;
    unsigned stop_after = 0;
    unsigned error_after = 0;
    void ReleaseFences() {
        ++calls;
        if (fulfill_after && calls >= fulfill_after) memory->word = 7;
        if (stop_after && calls >= stop_after) system->shutting_down = true;
        if (error_after && calls >= error_after) {
            Eden::RecordGpuFailure(std::make_exception_ptr(
                std::runtime_error("native GPU builder failed")));
        }
        assert(calls < 512 && "semaphore acquire must terminate");
    }
};
struct DmaPusher {
    Memory memory_manager;
    System system;
    Rasterizer* rasterizer;
    DmaPusher() : rasterizer(new Rasterizer{&memory_manager, &system}) {}
    ~DmaPusher() { delete rasterizer; }
};
struct Registers {
    struct Address { std::uint64_t SemaphoreAddress() const { return 0x1234; } } semaphore_address;
    u32 semaphore_acquire = 7;
    bool acquire_active = false;
    u32 acquire_value = 0;
    bool acquire_mode = true;
    bool acquire_source = true;
};
class Puller {
public:
    Registers regs;
    void ProcessSemaphoreAcquire(DmaPusher&);
};
INJECT
int main() {
    Eden::ResetGpuFailureForTitle();
    Puller p;
    DmaPusher matched;
    matched.memory_manager.word = 7;
    p.ProcessSemaphoreAcquire(matched);
    assert(matched.rasterizer->calls == 0 && !p.regs.acquire_active);
    DmaPusher finished;
    finished.rasterizer->fulfill_after = 3;
    p.ProcessSemaphoreAcquire(finished);
    assert(finished.rasterizer->calls == 3);
    assert(finished.memory_manager.reads == 4 && p.regs.acquire_active);
    assert(p.regs.acquire_value == 7 && !p.regs.acquire_mode && !p.regs.acquire_source);
    DmaPusher stopping;
    stopping.rasterizer->stop_after = 2;
    p.ProcessSemaphoreAcquire(stopping);
    assert(stopping.rasterizer->calls == 2 && stopping.system.shutting_down);
#if defined(PS5_NATIVE)
    DmaPusher failed;
    failed.rasterizer->error_after = 2;
    bool caught = false;
    try { p.ProcessSemaphoreAcquire(failed); }
    catch (const std::runtime_error&) { caught = true; }
    assert(caught && failed.rasterizer->calls >= 2 &&
           failed.rasterizer->calls <= 64);
    assert(Eden::PeekGpuFailure());
    Eden::ResetGpuFailureForTitle();
    DmaPusher already_failed;
    Eden::RecordGpuFailure(std::make_exception_ptr(
        std::runtime_error("persisted GPU builder failed")));
    caught = false;
    try { p.ProcessSemaphoreAcquire(already_failed); }
    catch (const std::runtime_error&) { caught = true; }
    assert(caught && already_failed.rasterizer->calls == 0);
    Eden::ResetGpuFailureForTitle();
#else
    // Non-console builds have no added fault check; shutdown is authoritative.
    DmaPusher host_failed;
    host_failed.rasterizer->error_after = 2;
    host_failed.rasterizer->stop_after = 3;
    p.ProcessSemaphoreAcquire(host_failed);
    assert(host_failed.rasterizer->calls == 3);
    Eden::ResetGpuFailureForTitle();
#endif
}
"""
compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-puller-failure-") as td:
    p=Path(td)
    for kind, source in (("release", QUIET), ("dev", DEV)):
        for platform in ("host", "native"):
            cpp=PROGRAM.replace("INJECT", method(source))
            file=p/f"{kind}-{platform}.cpp"
            exe=p/f"{kind}-{platform}"
            file.write_text(cpp)
            flags=["-DEDEN_DEV_PROFILE"] if kind=="dev" else []
            if platform=="native": flags.append("-DPS5_NATIVE")
            subprocess.run([compiler,"-std=c++20","-O1","-Wall","-Wextra",
                            "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                            "-pthread","-I",str(ROOT/"headless"),*flags,
                            str(file),"-o",str(exe)],check=True,timeout=70,
                           capture_output=True,text=True)
            run=subprocess.run([str(exe)],timeout=25,capture_output=True,text=True)
            assert run.returncode==0,(kind,platform,run.stdout[-800:],run.stderr[-1000:])
print("ENCORE_GPU_PULLER_FATAL_WAIT_PASS native=2 host=2 fatal=1 normal=1 stop=1 sanitized=1")
