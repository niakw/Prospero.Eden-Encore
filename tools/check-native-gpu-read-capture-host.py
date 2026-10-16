#!/usr/bin/env python3
"""Detect a queued GPU read callback retaining an unwound caller's stack.

The actual pinned GPU::Impl::OnCPURead method is compiled in a host fixture.
Failure before its queued callback runs must not leave a dangling read-area
reference. Original source is an ASan negative control, native capture passes.
No console build or game-performance claim.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
gpu = (root / "vendor/sources/eden/src/video_core/gpu.cpp").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
start = "    VideoCore::RasterizerDownloadArea OnCPURead(DAddr addr, u64 size) {"
end = "    /// Notify rasterizer that any caches of the specified region should be invalidated"
assert gpu.count(start) == 1 and gpu.count(end) == 1
body = start + gpu.split(start, 1)[1].split(end, 1)[0]
old = "RequestSyncOperation([this, &raster_area]() {"
fixed = "RequestSyncOperation([this, raster_area]() {"
assert body.count(old) == 1
assert cmake.count('set(gpu_read_capture_original "' + old + '")') == 1
assert cmake.count('string(REPLACE "${gpu_read_capture_original}"') == 1
assert cmake.count("Pinned GPU read callback lifetime changed") == 1
assert "python3 -B tools/check-native-gpu-read-capture-host.py" in workflow

cpp = r"""
#include <cassert>
#include <cstdint>
#include <functional>
#include <stdexcept>
#include <utility>
using DAddr = std::uint64_t;
using u64 = std::uint64_t;
namespace VideoCore {
struct RasterizerDownloadArea {
    DAddr start_address{};
    DAddr end_address{};
    bool preemtive{};
};
}
struct FakeRasterizer {
    VideoCore::RasterizerDownloadArea next_area{0x1000,0x2000,false};
    unsigned flushes{};
    VideoCore::RasterizerDownloadArea GetFlushArea(DAddr,u64) {
        return next_area;
    }
    void FlushRegion(DAddr a,u64 n) {
        assert(a == 0x1000 && n == 0x1000);
        ++flushes;
    }
};
struct FakeRenderer {
    FakeRasterizer raster;
    FakeRasterizer* ReadRasterizer() {return &raster;}
};
struct FakeThread {
    unsigned ticks{};
    void TickGPU(bool) {++ticks;}
};
struct FakeGPU {
    FakeRenderer store{};
    FakeRenderer* renderer = &store;
    FakeThread gpu_thread{};
    bool is_async = true;
    bool fail_wait = true;
    std::function<void()> pending{};
    template<class Fn> u64 RequestSyncOperation(Fn&& fn) {
        pending=std::forward<Fn>(fn);
        return 1;
    }
    void WaitForSyncOperation(u64 fence) {
        assert(fence == 1);
        if(fail_wait) throw std::runtime_error("GPU worker failure");
        assert(static_cast<bool>(pending));
        pending();
        pending={};
    }
@@METHOD@@
};
int main(int argc,char**) {
    if(argc > 1) {
        FakeGPU gpu;
        try {
            (void)gpu.OnCPURead(0x1100,16);
            assert(false && "wait should throw");
        } catch (const std::runtime_error&) {}
        assert(gpu.gpu_thread.ticks == 1);
        assert(gpu.store.raster.flushes == 0);
        // Simulate the pending callback outliving the failed caller stack.
        auto replay = std::move(gpu.pending);
        replay();
        assert(gpu.store.raster.flushes == 1);
        return 0;
    }
    FakeGPU gpu;
    gpu.fail_wait = false;
    auto area = gpu.OnCPURead(0x1100,16);
    assert(area.preemtive && gpu.gpu_thread.ticks == 1);
    assert(gpu.store.raster.flushes == 1 && !gpu.pending);
    gpu.store.raster.next_area.preemtive = true;
    auto fast = gpu.OnCPURead(0x1100,16);
    assert(fast.preemtive && gpu.gpu_thread.ticks == 1);
}
"""
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 required"
with tempfile.TemporaryDirectory(prefix="encore-read-capture-") as tmp:
    work = Path(tmp)
    for label, source_body, is_native in (
        ("pinned", body, False),
        ("native", body.replace(old,fixed), True),
    ):
        unit = work / (label + ".cpp")
        binary = work / label
        unit.write_text(cpp.replace("@@METHOD@@", source_body))
        subprocess.run(
            [clang, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
             "-Werror", "-fsanitize=address,undefined",
             "-fsanitize-address-use-after-return=always",
             "-fno-sanitize-recover=all", str(unit), "-o", str(binary)],
            check=True, timeout=45,
        )
        env = dict(os.environ, ASAN_OPTIONS="detect_stack_use_after_return=1")
        if is_native:
            subprocess.run([str(binary)], env=env, check=True, timeout=45)
            subprocess.run([str(binary), "--failed-wait"], env=env,
                           check=True, timeout=45)
        else:
            subprocess.run([str(binary)], env=env, check=True, timeout=45)
            broken = subprocess.run(
                [str(binary), "--failed-wait"], env=env,
                text=True, capture_output=True, timeout=45
            )
            assert broken.returncode != 0, "Original dangling capture was not detected"
            assert ("stack-use-after-return" in broken.stderr or
                    "stack-use-after-scope" in broken.stderr), broken.stderr
print("NATIVE_GPU_READ_CAPTURE_HOST_PASS original_stack_use_after_return=1 native_callback_owns_range=1 normal_wait=1 preemptive_skip=1 sanitizer=address_undefined")
