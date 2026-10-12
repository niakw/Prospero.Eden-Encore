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
assert "amd_distinct >= 5 && amd_distinct <= 8" in probe
assert "x2_distinct >= 5 && x2_distinct <= 8" in probe
assert "source_name = has_amd_topology ? \"x2apic_fallback\" : \"x2apic\"" in probe
assert "amd_classified == allowed_count" in probe
assert '"kern.sched.topology_spec"' in probe
assert '"kern.sched.ule.topology_spec"' in probe
assert "os_topology_valid" in probe
assert 'source_name = "freebsd_sched"' in probe
assert "ParseSmtGroups" in probe
assert "x2_classified == allowed_count" in probe
assert "cores.begin(), cores.end(), static_cast<unsigned>(cpu_core[cpu])" in probe
assert "if (!primary_core) secondary_cpus |= 1ULL << cpu;" in probe
print("PS5 worker topology: validated AMD/x2APIC plausible-source selection and scheduling point PASS")
