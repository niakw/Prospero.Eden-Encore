#!/usr/bin/env python3
"""Map critical headless runtime interfaces to their actual consumers.

The application owns these headers/fragments; they are not overrides of
pinned vendor code and must not be mechanically moved into encore-active.
This is a static dependency boundary check, not runtime/native proof.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADLESS = ROOT / "headless"
ENCORE = ROOT / "vendor/encore-active/eden-core/src"
g11_a32 = ENCORE / "core/arm/dynarmic/g11/arm_dynarmic_32_native_normal.cpp"
g11_a64_dev = ENCORE / "core/arm/dynarmic/g11/arm_dynarmic_64_native_dev.cpp"
physical_core = ENCORE / "core/hle/kernel/physical_core_standard.cpp"
main = HEADLESS / "main.cpp"
graphics = HEADLESS / "graphics.cpp"
performance = HEADLESS / "performance.cpp"
probe = HEADLESS / "gpu_probe.inc"

# Every declaration has concrete, explicitly checked consumers. Each entry
# is separate so another inclusion chain cannot accidentally replace it.
consumers = {
    "jit-startup-retry.h": (g11_a32, g11_a64_dev),
    "experimental_performance.h": (g11_a32, g11_a64_dev, main),
    "performance.h": (g11_a64_dev, main, graphics, performance),
    "gpu_fault_rate_limit.h": (main, performance),
    "guest_fault.h": (main, physical_core),
    "crash_site.h": (g11_a64_dev,),
    "cache_budget.h": (main,),
    "stall_watchdog.h": (main, performance),
    "gpu_probe.inc": (graphics,),
    "gpu_native_probe.inc": (probe,),
    "direct_pool_accounting.h": (performance,),
    "ps5_cpu_topology.h": (performance,),
}
assert len(consumers) == 12
for header, sources in consumers.items():
    content = (HEADLESS / header).read_text()
    assert content.strip(), header
    include = '#include "' + header + '"'
    for source in sources:
        assert include in source.read_text(), (
            "headless runtime interface consumer moved", header,
            str(source.relative_to(ROOT)))

native = (HEADLESS / "gpu_native_probe.inc").read_text()
assert 'void ProbeNativeQueue(unsigned memory_type)' in native
assert '#ifdef EDEN_GPU_PROBE\n#include "gpu_probe.inc"\n#endif' in graphics.read_text()
assert '#include "gpu_native_probe.inc"' in probe.read_text()
assert '#if defined(EDEN_DEV_PROFILE) && defined(PS5_NATIVE)' in (
    HEADLESS / "stall_watchdog.h").read_text()
assert 'return std::exchange(guest_fault, {});' in (
    HEADLESS / "guest_fault.h").read_text()
assert 'return n <= 8 || (n & (n - 1)) == 0;' in (
    HEADLESS / "gpu_fault_rate_limit.h").read_text()
assert 'std::uint32_t NextCapacity(' in (
    HEADLESS / "jit-startup-retry.h").read_text()
assert 'Core::' in g11_a32.read_text()
print("ENCORE_HEADLESS_CRITICAL_INTERFACE_OWNERS_PASS interfaces=12 consumers=" +
      str(sum(len(links) for links in consumers.values())) +
      " only_app_headers=1 native_runtime_unqualified=1")
