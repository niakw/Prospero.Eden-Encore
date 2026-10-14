#!/usr/bin/env python3
"""Native worker scheduling qualification and mocked-platform host fixture.

Both native release and diagnostic builds request SCHED_RR at priority 700.
Verify one attempt per native thread, readback and fail-open on refusal.
These host tests do not establish a hardware FPS or pause-freeze gain.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
perf = (root / "headless/performance.cpp").read_text()
header = (root / "headless/performance.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
scheduler = (root / "vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp").read_text()
graphics = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
compute = (root / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()

start = perf.index("void ProbeSchedulerOnce(const char* role) noexcept {")
end = perf.index("\nvoid SetSecondaryPlacement(bool enabled)", start)
probe = perf[start:end]
assert "void ProbeSchedulerOnce(const char* role) noexcept;" in header
assert probe.count("static thread_local bool reported = false;") == 1
assert probe.count("pthread_getschedparam(pthread_self()") == 1
assert probe.count("cpuset_getaffinity(") == 1
assert "SCHED_FIFO" in probe and "SCHED_RR" in probe
assert "EDEN_PS5_THREAD_SCHED" in probe
assert "pthread_setschedparam(pthread_self(), SCHED_RR, &priority)" in probe
assert "#if defined(EDEN_DEV_PROFILE)" not in probe
assert "rr_verified" in probe and "rr_error" in probe
assert "priority.sched_priority == 700" in probe
assert "cpuset_setaffinity" not in probe
assert scheduler.count('::Eden::Performance::ProbeSchedulerOnce("VulkanWorker");') == 1
assert scheduler.count('#include "performance.h"') == 1
for source in (graphics, compute):
    assert source.count('::Eden::Performance::ProbeSchedulerOnce("VkPipelineBuilder");') == 1
    assert '#ifdef PS5_NATIVE\n        ::Eden::Performance::ProbeSchedulerOnce' in source
assert generator.count('::Eden::Performance::ProbeSchedulerOnce("VulkanWorker");') == 1
assert generator.count('::Eden::Performance::ProbeSchedulerOnce("VkPipelineBuilder");') == 1
assert generator.count("sched_probe_anchor") == 3
assert '#ifdef PS5_NATIVE\n    ::Eden::Performance::ProbeSchedulerOnce' in scheduler

fixture = r"""
#include <atomic>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <pthread.h>
#include <sched.h>
#include <thread>
#define CPU_LEVEL_WHICH 1
#define CPU_WHICH_TID 1
#ifdef CPU_ISSET
#undef CPU_ISSET
#endif
struct cpuset_t { unsigned long long bits{}; };
#define CPU_ISSET(cpu, set) (((set)->bits & (1ULL << (cpu))) != 0)
int cpuset_getaffinity(int, int, int, size_t, cpuset_t* out) {
    out->bits = 0x1fffULL;
    return 0;
}
static thread_local int fake_policy = SCHED_FIFO;
static std::atomic<bool> deny_rr{false};
int fake_getschedparam(pthread_t, int* policy, sched_param* priority) {
    *policy = fake_policy;
    priority->sched_priority = 700;
    return 0;
}
int fake_setschedparam(pthread_t, int policy, const sched_param* priority) {
    assert(policy == SCHED_RR && priority->sched_priority == 700);
    if (deny_rr.load()) return EPERM;
    fake_policy = policy;
    return 0;
}
#define pthread_getschedparam fake_getschedparam
#define pthread_setschedparam fake_setschedparam
namespace Eden::Performance {
""" + probe + r"""
}
int main() {
    Eden::Performance::ProbeSchedulerOnce("VkPipelineBuilder");
    Eden::Performance::ProbeSchedulerOnce("VkPipelineBuilder");
    std::thread t([] { Eden::Performance::ProbeSchedulerOnce("VulkanWorker"); });
    t.join();
    deny_rr.store(true);
    std::thread denied([] { Eden::Performance::ProbeSchedulerOnce("FallbackWorker"); });
    denied.join();
}
"""

with tempfile.TemporaryDirectory() as tmp:
    cpp = Path(tmp) / "probe.cpp"
    cpp.write_text(fixture)
    exe = Path(tmp) / "probe"
    subprocess.run(
        ["c++", "-std=c++20", "-pthread", "-DPS5_NATIVE", "-DEDEN_DEV_PROFILE",
         str(cpp), "-o", str(exe)], check=True,
    )
    run = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
    records = run.stdout.strip().splitlines()
    assert len(records) == 3, records
    assert all(line.startswith("EDEN_PS5_THREAD_SCHED") for line in records), records
    assert all("allowed_mask=0x1fff" in line for line in records), records
    assert all("original_policy=" in line for line in records), records
    assert all("rr_attempted=1" in line for line in records), records
    assert all("rr_verified=1" in line for line in records[:2]), records
    assert "role=FallbackWorker" in records[-1] and "rr_verified=0" in records[-1], records
    assert "rr_error=1" in records[-1], records

    # Shipping builds must apply the same verified, fail-open RR request.
    subprocess.run(["c++", "-std=c++20", "-pthread", "-DPS5_NATIVE",
                    str(cpp), "-o", str(exe)], check=True)
    release = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
    records = release.stdout.strip().splitlines()
    assert len(records) == 3, records
    assert all("rr_attempted=1" in line for line in records), records
    assert all("rr_verified=1" in line for line in records[:2]), records
    assert "role=FallbackWorker" in records[-1] and "rr_verified=0" in records[-1], records

    # Ordinary desktop builds have no native scheduling side effects.
    subprocess.run(["c++", "-std=c++20", "-pthread", str(cpp), "-o", str(exe)], check=True)
    host = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
    assert not host.stdout, host.stdout
print("Native scheduler: release+diagnostic round-robin success/fallback, host no-op")
