#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""R406: compile the exact production active-wait timer under host ASan/UBSan.
Also check the selected maintained normal/DEV GPU DMA and puller callsites.
No Sony SDK, binary build, console or guest synchronization changes.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
perf = (root / "headless/performance.h").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
report = (root / "headless/performance.cpp").read_text()
start = perf.index("class DiagnosticActiveTimer {")
end = perf.index("// Guest OnCPUWrite", start)
impl = perf[start:end]
assert "active->store(start.count(), std::memory_order_release);" in impl
assert "active->store(0, std::memory_order_release);" in impl
assert "if (!totals) return;" in impl
assert "std::memory_order_acquire" in impl
assert "while (" not in impl and "std::printf(" not in impl
gpu_root = root / "vendor/encore-active/eden-core/src/video_core"
dma_normal = (gpu_root / "dma_pusher.cpp").read_text()
dma_dev = (gpu_root / "dma_pusher_dev.cpp").read_text()
puller_normal = (gpu_root / "engines/puller.cpp").read_text()
puller_dev = (gpu_root / "engines/puller_dev.cpp").read_text()
assert 'list(APPEND video_sources "${EDEN_MAINTAINED_GPU_DMA}" "${EDEN_MAINTAINED_GPU_PULLER}")' in cmake
assert 'dma_pusher_dev.cpp' in cmake and 'engines/puller_dev.cpp' in cmake
for text in (dma_normal, dma_dev):
    assert "sync_cv.wait_for(lk, std::chrono::milliseconds(10))" in text
for text in (puller_normal, puller_dev):
    assert "word != value && !dma_pusher.system.IsShuttingDown()" in text
assert "gpu_dma_sync_active_since_ns" in dma_dev
assert "gpu_puller_semaphore_active_since_ns" in puller_dev
for text in (dma_normal, puller_normal):
    assert "DiagnosticActiveTimer" not in text
for text in (dma_dev, puller_dev):
    assert "DiagnosticActiveTimer" in text
assert "EDEN_GPU_PULLER_SEMAPHORE frame=%u calls=%llu ns=%llu active_ns=%llu" in report
assert "EDEN_GPU_DMA_SYNC frame=%u calls=%llu ns=%llu active_ns=%llu" in report

cpp = r"""
#include <atomic>
#include <chrono>
#include <cassert>
#include <cstdint>
namespace Common {
struct Clock {
    std::atomic<long long> current{1'000'000};
    std::atomic<unsigned> reads{0};
    std::chrono::nanoseconds GetTimeNS() noexcept {
        reads.fetch_add(1, std::memory_order_relaxed);
        return std::chrono::nanoseconds{current.load(std::memory_order_relaxed)};
    }
};
inline Clock g_wall_clock;
}
namespace Eden::Performance {
struct Totals { std::atomic<unsigned long long> calls{}, nanoseconds{}, requested_bytes{}; };
inline std::atomic<bool> detailed_gpu_profile{false};
__IMPL__
}
int main() {
    using namespace Eden::Performance;
    Totals totals;
    std::atomic<long long> active{0};
    // When disabled or already satisfied, there are no clocks or writes.
    { DiagnosticActiveTimer t(totals, active, true); }
    assert(Common::g_wall_clock.reads == 0 && active == 0 && totals.calls == 0);
    detailed_gpu_profile = true;
    { DiagnosticActiveTimer t(totals, active, false); }
    assert(Common::g_wall_clock.reads == 0 && active == 0 && totals.calls == 0);
    {
        DiagnosticActiveTimer t(totals, active, true);
        assert(active == 1'000'000);
        Common::g_wall_clock.current = 10'000'000;
        assert(ActiveDiagnosticWaitNs(active) == 9'000'000);
    }
    assert(active == 0);
    assert(ActiveDiagnosticWaitNs(active) == 0);
    assert(totals.calls == 1 && totals.nanoseconds == 9'000'000);
    // A subsequent wait reuses the active slot without inventing stale time.
    Common::g_wall_clock.current = 12'000'000;
    { DiagnosticActiveTimer t(totals, active, true);
      Common::g_wall_clock.current = 12'250'000; }
    assert(totals.calls == 2 && totals.nanoseconds == 9'250'000);
    assert(active == 0);
}
""".replace("__IMPL__", impl)
compiler = next((v for v in ("clang++-18", "clang++", "g++") if shutil.which(v)), None)
if compiler is None:
    raise SystemExit("C++20 compiler not available")
env = os.environ.copy()
if sys.platform == "darwin" and "SDKROOT" not in env:
    sdk = Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk")
    if sdk.is_dir():
        env["SDKROOT"] = str(sdk)
with tempfile.TemporaryDirectory(prefix="eden-r406-gpu-livewait-") as temp:
    source = Path(temp) / "wait.cpp"
    target = Path(temp) / "wait"
    source.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    str(source), "-o", str(target)], check=True, timeout=90, env=env)
    subprocess.run([str(target)], check=True, timeout=30, env=env)
print("PASS R406 source-extracted active GPU waits ASan/UBSan, quiet, satisfied, ongoing, completed")
