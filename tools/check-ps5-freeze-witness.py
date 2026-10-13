#!/usr/bin/env python3
"""R376: source-extracted host test for independent GPU freeze witness."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
performance = (root / "headless/performance.cpp").read_text()
pad = (root / "headless/pad.cpp").read_text()
start = performance.index("bool GpuReportStale(")
end = performance.index("\nvoid ReportInputThreadGpuLiveness()", start)
body = performance[start:end]
assert 'kStallNs = 20' in body
assert 'progress_ns != 0' in body
assert 'now_ns > progress_ns' in body
assert 'now_ns - progress_ns >= kStallNs' in body
assert 'if (!detailed_gpu_profile.load(std::memory_order_relaxed)) return;' in performance
assert 'latest_gpu_report_frame.store(frame' in performance
assert 'if (detailed_gpu_profile.load(std::memory_order_relaxed)) {' in performance
assert 'latest_gpu_report_ns.store(' in performance
assert 'std::memory_order_release' in performance
assert 'std::memory_order_acquire' in performance
assert 'EDEN_GPU_REPORT_STALLED' in performance
assert 'dma_active_ms=%llu puller_active_ms=%llu' in performance
assert 'ActiveDiagnosticWaitNs(gpu_dma_sync_active_since_ns)' in performance
assert 'ActiveDiagnosticWaitNs(gpu_puller_semaphore_active_since_ns)' in performance
watch = (root / "headless/stall_watchdog.h").read_text()
assert 'EDEN_GAME_GPU_STALL_SUSPECT' in watch
assert 'dma_active_ms=%llu puller_active_ms=%llu note=diagnostic_only' in watch
assert 'Performance::ActiveDiagnosticWaitNs(' in watch
assert 'if (observation.suspected)' in watch
assert 'if (Performance::detailed_gpu_profile.load(std::memory_order_relaxed))' in watch
assert 'gpu_command_tick.calls.load' in performance
assert 'guest_cpu_write.calls.load' in performance
assert 'guest_dequeue_wait.calls.load' in performance
assert 'gpu_command_tick.calls.store' not in performance
assert 'Performance::ReportInputThreadGpuLiveness();' in pad
assert pad.index('if (NativeLogs::Detailed() && polls % 1250 == 0)') < \
    pad.index('Performance::ReportInputThreadGpuLiveness();') < \
    pad.index('"EDEN_PAD_HEARTBEAT')
source = '''
#include <cassert>
#include <cstdint>
''' + body + '''
int main() {
    // No report yet, never falsely claim a freeze during title startup.
    assert(!GpuReportStale(0, 0));
    assert(!GpuReportStale(30'000'000'000ULL, 0));
    assert(!GpuReportStale(10, 11));
    constexpr unsigned long long now = 200'000'000'000ULL;
    assert(!GpuReportStale(now, now));
    assert(!GpuReportStale(now + 19'999'999'999ULL, now));
    assert(GpuReportStale(now + 20'000'000'000ULL, now));
    assert(GpuReportStale(now + 350'000'000'000ULL, now));
    assert(!GpuReportStale(1, 900'000'000'000ULL)); // wrapped/clock reset
}
'''
env = os.environ.copy()
if sys.platform == "darwin" and not env.get("SDKROOT"):
    sdk = Path("/Library/Developer/CommandLineTools/SDKs/MacOSX15.4.sdk")
    if sdk.exists():
        env["SDKROOT"] = str(sdk)
with tempfile.TemporaryDirectory(prefix="eden-r376-witness-") as temp:
    cpp = Path(temp) / "witness.cpp"
    binary = Path(temp) / "witness"
    cpp.write_text(source)
    subprocess.run(["c++", "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", str(cpp), "-o", str(binary)],
                   check=True, timeout=30, env=env)
    subprocess.run([str(binary)], check=True, timeout=12, env=env)
print("PASS R376 GPU report stale threshold: independent 20s witness, quiet-path guards, no locks")
