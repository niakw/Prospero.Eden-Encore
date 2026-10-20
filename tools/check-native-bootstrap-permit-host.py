#!/usr/bin/env python3
"""Source-extracted bootstrap Initialize/Unload context permit ownership."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "vendor/encore-active/eden-threading/src/core/hle/kernel/k_scheduler.cpp").read_text()


def method(begin, end):
    assert source.count(begin) == source.count(end) == 1
    return begin + source.split(begin, 1)[1].split(end, 1)[0]


initialize = method("void KScheduler::Initialize(", "void KScheduler::Activate(")
unload = method("void KScheduler::Unload(", "void KScheduler::Reload(")
claim = """    // CPU workers enter the bootstrap fiber before the normal acquisition loop.
    // Its first Unload must return an owned context permit.
    if (!main_thread->m_context_guard.try_acquire()) {
        UNREACHABLE_MSG("Bootstrap thread context permit is already held");
    }

"""
assert initialize.count(claim) <= 1
original = initialize.replace(claim, "")
cpp = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <semaphore>
using s32 = std::int32_t;
using u32 = std::uint32_t;
#define UNREACHABLE_MSG(...) std::abort()
namespace Kernel {
enum class DpcFlag : unsigned { Terminated = 1 };
struct KThread {
    std::binary_semaphore m_context_guard{1};
    struct Stack { unsigned dpc_flags = 0; } stack;
    Stack& GetStackParameters() { return stack; }
};
struct Core {
    unsigned saves = 0;
    void SaveContext(KThread* thread) { assert(thread); ++saves; }
};
struct KernelCore {
    Core core;
    Core& PhysicalCore(s32 id) { assert(id == 2); return core; }
};
struct KScheduler {
    s32 m_core_id = -1;
    KThread* m_idle_thread = nullptr;
    KThread* m_current_thread = nullptr;
    void Initialize(KernelCore&, KThread*, KThread*, s32);
    void Unload(KernelCore&, KThread*);
};
INITIALIZE
UNLOAD
}
int main() {
    using namespace Kernel;
    for (unsigned repeat = 0; repeat < 64; ++repeat) {
        KernelCore kernel;
        KThread bootstrap, idle;
        KScheduler scheduler;
        scheduler.Initialize(kernel, &bootstrap, &idle, 2);
        assert(scheduler.m_current_thread == &bootstrap && scheduler.m_idle_thread == &idle);
        // The first active fiber must already own its context permit.
        assert(!bootstrap.m_context_guard.try_acquire());
        assert(idle.m_context_guard.try_acquire());
        idle.m_context_guard.release();
        scheduler.Unload(kernel, &bootstrap);
        assert(kernel.core.saves == 1);
        assert(bootstrap.m_context_guard.try_acquire());
        assert(!bootstrap.m_context_guard.try_acquire());
        // A terminated context never returns a permit for reuse.
        bootstrap.stack.dpc_flags = unsigned(DpcFlag::Terminated);
        scheduler.Unload(kernel, &bootstrap);
        assert(kernel.core.saves == 2);
        assert(!bootstrap.m_context_guard.try_acquire());
    }
    std::puts("BOOTSTRAP_CONTEXT_PERMIT_PASS lifecycles=64 idle_free=1 terminated_not_reused=1");
}
"""
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-bootstrap-permit-") as temp:
    folder = Path(temp)
    for label, body in (("original", original), ("maintained", initialize)):
        path, executable = folder / (label + ".cpp"), folder / label
        path.write_text(cpp.replace("INITIALIZE", body).replace("UNLOAD", unload))
        subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-fsanitize=address,undefined",
                        "-fno-sanitize-recover=all", str(path), "-o", str(executable)],
                       check=True, timeout=60)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
        if label == "original":
            assert result.returncode != 0 and "Assertion" in result.stderr, result.stderr
            print("ORIGINAL_BOOTSTRAP_UNCLAIMED_PERMIT_WITNESS_PASS")
        else:
            assert result.returncode == 0, result.stderr
            assert initialize.count(claim) == 1, "bootstrap claim missing"
            print(result.stdout, end="")
print("BOOTSTRAP_PERMIT_HOST_ONLY PS5_guest_progress=unverified")
