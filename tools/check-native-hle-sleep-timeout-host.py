#!/usr/bin/env python3
"""Run the actual pinned and native SleepThread under UBSan with mocked HLE state.

Catches signed-deadline overflow and verifies ordinary sleeps/yields. Host only.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/core/hle/kernel/svc/svc_thread.cpp").read_text()
native = (root / "vendor/encore-active/eden-threading/src/core/hle/kernel/svc/svc_thread.cpp").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert 'list(APPEND eden_svc_sleep_sources ' in cmake and 'eden_checked_sleep' in cmake
assert "python3 -B tools/check-native-hle-sleep-timeout-host.py" in workflow
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler

old = """            timeout = kernel.HardwareTimer().GetTick() + offset_tick + 2;
            if (timeout <= 0) {
                timeout = (std::numeric_limits<s64>::max)();
            }"""
replacement = """            s64 absolute{};
            if (__builtin_add_overflow(kernel.HardwareTimer().GetTick(), offset_tick,
                                       &absolute) ||
                __builtin_add_overflow(absolute, s64{2}, &absolute) || absolute <= 0) {
                timeout = (std::numeric_limits<s64>::max)();
            } else {
                timeout = absolute;
            }"""
assert pinned.count(old) == 1
assert native == pinned.replace(old, replacement)

def sleep(source):
    start = "void SleepThread(Core::System& system, s64 ns) {"
    end = "/// Gets the thread context"
    assert source.count(start) == source.count(end) == 1
    return start + source.split(start, 1)[1].split(end, 1)[0].strip() + "\n"

prelude = r"""
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <limits>
using s64 = std::int64_t;
namespace Kernel {
struct KernelCore {
    struct Timer {
        s64 now{};
        s64 GetTick() const { return now; }
    } timer;
    Timer& HardwareTimer() { return timer; }
    int sleep_calls{};
    s64 last_deadline{};
    int yield_kind{};
};
struct KThread {
    int Sleep(KernelCore& kernel, s64 deadline) {
        ++kernel.sleep_calls;
        kernel.last_deadline = deadline;
        return 0;
    }
};
KThread& GetCurrentThread(KernelCore&) { static KThread thread; return thread; }
struct KScheduler {
    static void YieldWithoutCoreMigration(KernelCore& k) { k.yield_kind = 1; }
    static void YieldWithCoreMigration(KernelCore& k) { k.yield_kind = 2; }
    static void YieldToAnyThread(KernelCore& k) { k.yield_kind = 3; }
};
namespace Svc {
enum class YieldType : s64 {
    WithoutCoreMigration = -1, WithCoreMigration = -2, ToAnyThread = -3
};
}
}
namespace Core {
struct System {
    Kernel::KernelCore kernel;
    Kernel::KernelCore& Kernel() { return kernel; }
};
}
#define LOG_TRACE(...) ((void)0)
namespace Kernel::Svc {
"""
postlude = r"""
} // namespace Kernel::Svc
int main(int argc, char** argv) {
    assert(argc == 2);
    const int mode = std::atoi(argv[1]);
    const s64 max = (std::numeric_limits<s64>::max)();
    Core::System system;
    auto& kernel = system.Kernel();
    if (mode == 0) {
        kernel.timer.now = 100;
        Kernel::Svc::SleepThread(system, 5);
        assert(kernel.sleep_calls == 1 && kernel.last_deadline == 107);
        Kernel::Svc::SleepThread(system, 0);
        assert(kernel.sleep_calls == 1 && kernel.yield_kind == 0);
        Kernel::Svc::SleepThread(system, -1);
        assert(kernel.yield_kind == 1);
        Kernel::Svc::SleepThread(system, -2);
        assert(kernel.yield_kind == 2);
        Kernel::Svc::SleepThread(system, -3);
        assert(kernel.yield_kind == 3);
        Kernel::Svc::SleepThread(system, -4);
        assert(kernel.yield_kind == 3 && kernel.sleep_calls == 1);
    } else if (mode == 1) {
        kernel.timer.now = 100;
        volatile s64 huge = max;
        Kernel::Svc::SleepThread(system, huge);
#if EXPECT_FIXED
        assert(kernel.sleep_calls == 1 && kernel.last_deadline == max);
#endif
    } else if (mode == 2) {
        kernel.timer.now = max - 1;
        volatile s64 tiny = 1;
        Kernel::Svc::SleepThread(system, tiny);
#if EXPECT_FIXED
        assert(kernel.sleep_calls == 1 && kernel.last_deadline == max);
#endif
    } else if (mode == 3) {
        kernel.timer.now = max - 4;
        Kernel::Svc::SleepThread(system, 1);
        assert(kernel.sleep_calls == 1 && kernel.last_deadline == max - 1);
    } else if (mode == 4) {
        kernel.timer.now = max - 2;
        volatile s64 tiny = 1;
        Kernel::Svc::SleepThread(system, tiny);
#if EXPECT_FIXED
        assert(kernel.sleep_calls == 1 && kernel.last_deadline == max);
#endif
    } else return 9;
}
"""
with tempfile.TemporaryDirectory(prefix="encore-native-sleep-") as td:
    d = Path(td)
    for label, source, fixed in (("pinned", pinned, False), ("native", native, True)):
        cpp, exe = d / (label + ".cpp"), d / label
        cpp.write_text(prelude + sleep(source) + postlude)
        subprocess.run([compiler, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", "-fno-sanitize-recover=undefined",
                        "-DEXPECT_FIXED=" + str(int(fixed)), str(cpp), "-o", str(exe)],
                       check=True, timeout=30)
        for mode in range(5):
            result = subprocess.run([str(exe), str(mode)], capture_output=True,
                                    text=True, timeout=10)
            if not fixed and mode in (1, 2, 4):
                assert result.returncode != 0, (label, mode, result.stderr)
                assert "runtime error: signed integer overflow" in result.stderr, (
                    label, mode, result.stderr)
            else:
                assert result.returncode == 0, (label, mode, result.stdout, result.stderr)
        print("NATIVE_SLEEP_TIMEOUT_SATURATION_PASS" if fixed
              else "PINNED_SLEEP_TIMEOUT_UBSAN_WITNESS_PASS")
print("SLEEP_TIMEOUT_HOST_ONLY_NO_CONSOLE_OR_GUEST_PROGRESS_PROOF")
