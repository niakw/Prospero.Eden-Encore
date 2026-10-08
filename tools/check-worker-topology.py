#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
text = (root / "headless/performance.cpp").read_text()
start = text.index("void CheckWorkerTopology()")
end = text.index("void PlaceSecondary(", start)
probe = text[start:end]

for needle in (
    "cpuset_setaffinity",
    "sched_yield();",
    "std::this_thread::sleep_for(std::chrono::milliseconds(1));",
    "__cpuid_count(0xb",
    "secondary_cpus = 0;",
    "Cannot restore topology-probe thread affinity",
):
    assert needle in probe, needle

assert probe.index("sched_yield();") < probe.index("__cpuid_count(0xb")
assert probe.index("sleep_for(std::chrono::milliseconds(1))") < probe.index("__cpuid_count(0xb")
print("PS5 worker-topology probe forces a scheduling point before x2APIC sampling: PASS")
