#!/usr/bin/env python3
"""Source-extracted C++20 test: quiet guest-core/graphics counters never write."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
content = (root / "headless/performance.h").read_text()
def extract(start: str, end: str) -> str:
    assert content.count(start) == 1, start
    return content.split(start, 1)[1].split(end, 1)[0]

idle = "inline void CountIdle(" + extract("inline void CountIdle(", "\n// Development: reads")
condition = "inline void CountCondition(" + extract("inline void CountCondition(", "\ninline bool BootTrace")
assert "detailed_gpu_profile.load(std::memory_order_relaxed)" in idle
assert "detailed_gpu_profile.load(std::memory_order_relaxed)" in condition
assert "guest_idle[core].calls.fetch_add" in idle
assert "render_conditions[slot].fetch_add" in condition
compiler = shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "clang++ is required for sanitizer witness"
fixture = r"""
#include <atomic>
#include <array>
#include <cstddef>
#include <cassert>
inline std::atomic<bool> detailed_gpu_profile{false};
struct IdleCounters {
    std::atomic<unsigned long long> calls{0}, nanoseconds{0}, sleeps{0};
};
inline std::array<IdleCounters, 4> guest_idle{};
inline std::array<std::atomic<unsigned long long>, 20> render_conditions{};
__IDLE__
__CONDITION__
int main() {
    for (unsigned i=0; i<100000; ++i) {
        CountIdle(1, 100, true);
        CountCondition(3);
    }
    assert(guest_idle[1].calls.load()==0);
    assert(guest_idle[1].nanoseconds.load()==0);
    assert(guest_idle[1].sleeps.load()==0);
    assert(render_conditions[3].load()==0);
    detailed_gpu_profile.store(true);
    CountIdle(1, 125, true);
    CountIdle(1, 75, false);
    CountIdle(4, 500, true);
    CountCondition(3);
    CountCondition(20);
    assert(guest_idle[1].calls.load()==2);
    assert(guest_idle[1].nanoseconds.load()==200);
    assert(guest_idle[1].sleeps.load()==1);
    assert(render_conditions[3].load()==1);
    detailed_gpu_profile.store(false);
    CountIdle(1, 90, true);
    CountCondition(3);
    assert(guest_idle[1].calls.load()==2);
    assert(render_conditions[3].load()==1);
}
""".replace("__IDLE__", idle).replace("__CONDITION__", condition)
with tempfile.TemporaryDirectory(prefix="eden-quiet-counter-") as d:
    file = Path(d) / "counter.cpp"
    exe = Path(d) / "counter"
    file.write_text(fixture)
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    str(file), "-o", str(exe)], check=True, timeout=90)
    subprocess.run([str(exe)], check=True, timeout=90)
print("NATIVE_QUIET_COUNTERS_HOST_PASS idle_off=1 condition_off=1 diagnostic_on=1 sanitizer=1")
