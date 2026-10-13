#!/usr/bin/env python3
"""R417: native Vulkan thread scheduling probe source + mocked-PS5 host fixture.

Validates read-only worker instrumentation and one log per real OS thread.
Host tests do NOT prove PS5 SMT topology, actual policy, or gameplay speed.
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
assert "pthread_setschedparam" not in probe
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
    out->bits = 0x1003ULL;
    return 0;
}
namespace Eden::Performance {
""" + probe + r"""
}
int main() {
    Eden::Performance::ProbeSchedulerOnce("VkPipelineBuilder");
    Eden::Performance::ProbeSchedulerOnce("VkPipelineBuilder");
    std::thread t([] { Eden::Performance::ProbeSchedulerOnce("VulkanWorker"); });
    t.join();
}
"""

with tempfile.TemporaryDirectory() as tmp:
    cpp = Path(tmp) / "probe.cpp"
    cpp.write_text(fixture)
    exe = Path(tmp) / "probe"
    subprocess.run(
        ["c++", "-std=c++20", "-pthread", "-DPS5_NATIVE", str(cpp), "-o", str(exe)],
        check=True,
    )
    run = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
    records = run.stdout.strip().splitlines()
    assert len(records) == 2, records
    assert all(line.startswith("EDEN_PS5_THREAD_SCHED") for line in records), records
    assert any("role=VkPipelineBuilder" in line for line in records), records
    assert any("role=VulkanWorker" in line for line in records), records
    assert all("allowed_mask=0x1003" in line for line in records), records

    # Plain desktop build remains a genuine no-op.
    subprocess.run(["c++", "-std=c++20", "-pthread", str(cpp), "-o", str(exe)], check=True)
    host = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
    assert not host.stdout, host.stdout
print("R417 scheduling probe: source and host fixture OK")
