#!/usr/bin/env python3
"""Host UBSan witnesses for native HLE guest-wait deadline saturation.

Compile the actual deadline arithmetic copied directly from the pinned and
maintained SVC C++ sources. Cover normal, zero, infinite, boundary and
out-of-range positive waits. The original synchronization path silently
produces a negative deadline; the two others trigger UBSan signed overflow.
No game-progress, console or on-device timeout claim is implied.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
base = root / "vendor/sources/eden/src/core/hle/kernel/svc"
native = root / "vendor/encore-active/eden-threading/src/core/hle/kernel/svc"
cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/verify/hle/check-native-hle-wait-timeout-host.py" in workflow
module = (root/"vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
assert "native-hle-overrides.cmake" in cmake
assert all(name in module for name in ("svc_condition_variable.cpp", "svc_address_arbiter.cpp", "svc_synchronization.cpp"))
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler

old_condvar = """            timeout = system.Kernel().HardwareTimer().GetTick() + offset_tick + 2;
            if (timeout <= 0) {
                timeout = (std::numeric_limits<s64>::max)();
            }"""
fix_condvar = """            s64 absolute{};
            if (__builtin_add_overflow(system.Kernel().HardwareTimer().GetTick(), offset_tick,
                                       &absolute) ||
                __builtin_add_overflow(absolute, s64{2}, &absolute) || absolute <= 0) {
                timeout = (std::numeric_limits<s64>::max)();
            } else {
                timeout = absolute;
            }"""
old_sync = """        u64 ticks = system.Kernel().HardwareTimer().GetTick();
        ticks += timeout_ns;
        ticks += 2;

        timeout = ticks;"""
fix_sync = """        s64 absolute{};
        if (__builtin_add_overflow(system.Kernel().HardwareTimer().GetTick(), s64{timeout_ns},
                                   &absolute) ||
            __builtin_add_overflow(absolute, s64{2}, &absolute) || absolute <= 0) {
            timeout = (std::numeric_limits<s64>::max)();
        } else {
            timeout = absolute;
        }"""

cases = {
    "svc_condition_variable.cpp": (
        "    // Convert timeout from nanoseconds to ticks.\n",
        "    // Wait on the condition variable.",
        old_condvar, fix_condvar, True),
    "svc_address_arbiter.cpp": (
        "    // Convert timeout from nanoseconds to ticks.\n",
        "    R_RETURN(", old_condvar, fix_condvar, True),
    "svc_synchronization.cpp": (
        "    // Convert the timeout from nanoseconds to ticks.\n",
        "    // Wait on the objects.", old_sync, fix_sync, False)
}

prelude = r"""
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <limits>
using s64 = std::int64_t;
using u64 = std::uint64_t;
struct Timer {
    s64 now{};
    s64 GetTick() const { return now; }
};
struct KernelCore {
    Timer timer;
    Timer& HardwareTimer() { return timer; }
};
struct System {
    KernelCore kernel;
    KernelCore& Kernel() { return kernel; }
};
s64 Convert(System& system, s64 timeout_ns) {
"""
postlude = r"""
    return timeout;
}
int main(int argc, char** argv) {
    assert(argc == 2);
    System system;
    const int mode = std::atoi(argv[1]);
    const s64 maximum = (std::numeric_limits<s64>::max)();
    if (mode == 0) {
        system.kernel.timer.now = 100;
        assert(Convert(system, 20) == 122);
        assert(Convert(system, 0) == 0);
        assert(Convert(system, -1) == -1);
        assert(Convert(system, -5) == -5);
        system.kernel.timer.now = maximum - 3;
        assert(Convert(system, 1) == maximum);
    } else if (mode == 1) {
        system.kernel.timer.now = 100;
        volatile s64 huge = maximum;
        const s64 value = Convert(system, huge);
#if EXPECT_FIXED
        assert(value == maximum);
#else
        assert(value < 0);
#endif
    } else if (mode == 2) {
        system.kernel.timer.now = maximum - 1;
        volatile s64 tiny = 1;
        const s64 value = Convert(system, tiny);
#if EXPECT_FIXED
        assert(value == maximum);
#else
        assert(value < 0);
#endif
    } else {
        return 9;
    }
}
"""

def extract(source, start, stop):
    assert source.count(start) == 1, "conversion marker missing or duplicated"
    tail = source.split(start, 1)[1]
    assert tail.count(stop) >= 1
    return tail.split(stop, 1)[0].strip() + "\n"

with tempfile.TemporaryDirectory(prefix="encore-native-svc-timeout-") as td:
    temporary = Path(td)
    for name, (start, stop, old, fixed, ub) in cases.items():
        pinned = (base / name).read_text()
        maintained = (native / name).read_text()
        assert pinned.count(old) == 1, "pinned SVC deadline source drift: " + name
        assert maintained == pinned.replace(old, fixed), (
            "maintained SVC not exact pinned + deadline check: " + name)
        for label, source, is_fixed in (("pinned", pinned, False),
                                        ("native", maintained, True)):
            cpp = temporary / (label + "-" + name)
            exe = temporary / (label + "-" + name + ".bin")
            cpp.write_text(prelude + extract(source, start, stop) + postlude)
            subprocess.run([compiler, "-std=c++20", "-O1", "-Wall", "-Wextra",
                            "-Werror", "-fsanitize=undefined",
                            "-fno-sanitize-recover=undefined",
                            "-DEXPECT_FIXED=" + str(int(is_fixed)), str(cpp),
                            "-o", str(exe)], check=True, timeout=30)
            for mode in range(3):
                result = subprocess.run([str(exe), str(mode)], capture_output=True,
                                        text=True, timeout=10)
                if not is_fixed and mode > 0 and ub:
                    assert result.returncode != 0, (name, label, mode, result.stderr)
                    assert "runtime error: signed integer overflow" in result.stderr, (
                        name, mode, result.stderr)
                else:
                    assert result.returncode == 0, (
                        name, label, mode, result.stdout, result.stderr)
            print(name + " " +
                  ("NATIVE_SVC_TIMEOUT_SATURATION_PASS" if is_fixed else
                   "PINNED_SVC_TIMEOUT_BOUNDARY_WITNESS_PASS"))
print("NATIVE_HLE_SVC_TIMEOUT_HOST_ONLY_NO_CONSOLE_PROOF")
