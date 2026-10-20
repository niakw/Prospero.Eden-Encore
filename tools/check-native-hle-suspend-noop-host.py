#!/usr/bin/env python3
"""ASan/UBSan proof for the real KThread::UpdateState suspend-flag no-op fast path.

Compares pinned/maintained source, including the scheduler notification boundary.
Counts relaxed atomic operations; no guest execution / console FPS claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = (ROOT / "vendor/sources/eden/src/core/hle/kernel/k_thread.cpp").read_text()
ACTIVE = (ROOT / "vendor/encore-active/eden-threading/src/core/hle/kernel/k_thread.cpp").read_text()
CMAKE = (ROOT / "vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
ORACLE = (ROOT / "tools/verify/hle/check-hle-overlay-layout.py").read_text()
FAST = (ROOT / ".github/workflows/encore-core-fast-gate.yml").read_text()
FULL = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()
SCRIPT = "python3 -B tools/check-native-hle-suspend-noop-host.py"
assert SCRIPT in FAST and SCRIPT in FULL
assert '"hle/kernel/k_thread.cpp" "core/hle/kernel/k_thread.cpp"' in CMAKE
assert "update_before" in ORACLE and "update_after" in ORACLE
assert "update_before, update_after" in ORACLE

START = "    void KThread::UpdateState(KernelCore& kernel) {"
END = "\n    void KThread::Continue(KernelCore& kernel) {"
def extract(source):
    assert source.count(START) == source.count(END) == 1
    return source[source.index(START):source.index(END)].rstrip()

old = extract(PIN)
new = extract(ACTIVE)
assert old.count("m_thread_state.store(new_state, std::memory_order_relaxed);") == 1
assert new.count("m_thread_state.store(new_state, std::memory_order_relaxed);") == 1
assert old.index("m_thread_state.store(new_state") < old.index("if (new_state != old_state)")
assert new.index("m_thread_state.store(new_state") > new.index("if (new_state != old_state)")
assert new.count("KScheduler::OnThreadStateChanged(kernel, this, old_state);") == 1
# Avoid accepting a broader behavioral drift from upstream in this test.
assert ACTIVE.count("void KThread::Continue(KernelCore& kernel)") == 1
assert PIN.count("void KThread::Continue(KernelCore& kernel)") == 1

CPP = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
using u16 = std::uint16_t;
#define ASSERT(x) assert(x)
enum class ThreadState : u16 {
    Initialized=0, Waiting=1, Runnable=2, Terminated=3,
    Mask=15, ProcessSuspended=16, ThreadSuspended=32, DebugSuspended=64
};
constexpr ThreadState operator&(ThreadState a, ThreadState b) {
    return static_cast<ThreadState>(static_cast<u16>(a)&static_cast<u16>(b));
}
constexpr ThreadState operator|(ThreadState a, ThreadState b) {
    return static_cast<ThreadState>(static_cast<u16>(a)|static_cast<u16>(b));
}
struct KernelCore { bool locked=true; };
struct KThread;
struct KScheduler {
    static bool IsSchedulerLockedByCurrentThread(KernelCore& k) { return k.locked; }
    static void OnThreadStateChanged(KernelCore&, KThread*, ThreadState);
};
struct TrackedAtomic {
    ThreadState value{};
    unsigned loads{}, stores{};
    ThreadState load(std::memory_order) { ++loads; return value; }
    void store(ThreadState v, std::memory_order) { ++stores; value=v; }
};
struct KThread {
    TrackedAtomic m_thread_state{};
    ThreadState requested{};
    ThreadState previous{};
    unsigned notifications{};
    ThreadState GetSuspendFlags() const { return requested; }
    void UpdateState(KernelCore&);
};
void KScheduler::OnThreadStateChanged(KernelCore& k, KThread* t, ThreadState old) {
    assert(k.locked);
    ++t->notifications;
    t->previous=old;
}
INJECT
int main() {
    KernelCore kernel{};
    constexpr std::array<u16, 5> flags{0,16,32,48,112};
    unsigned cases=0, noops=0, transitions=0;
    for (u16 old_flags: flags) {
      for (u16 next_flags: flags) {
        for (u16 state=0; state<4; ++state) {
            KThread t;
            const ThreadState old_state=static_cast<ThreadState>(old_flags|state);
            const ThreadState new_state=static_cast<ThreadState>(next_flags|state);
            t.m_thread_state.value=old_state;
            t.requested=static_cast<ThreadState>(next_flags);
            const bool changed=(new_state!=old_state);
            t.UpdateState(kernel);
            assert(t.m_thread_state.value==new_state);
            assert(t.m_thread_state.loads==1);
            assert(t.m_thread_state.stores==(changed ? 1u : NOOP_STORES));
            assert(t.notifications==(changed ? 1u : 0u));
            if (changed) assert(t.previous==old_state);
            const auto first_stores=t.m_thread_state.stores;
            t.UpdateState(kernel); // Now a no-op for every combination.
            assert(t.m_thread_state.value==new_state);
            assert(t.m_thread_state.loads==2);
            assert(t.m_thread_state.stores==first_stores+NOOP_STORES);
            assert(t.notifications==(changed ? 1u : 0u));
            if(changed) ++transitions; else ++noops;
            ++cases;
        }
      }
    }
    assert(cases==100 && transitions==80 && noops==20);
    std::printf("ENCORE_HLE_SUSPEND_NOOP_PASS cases=%u noop=%u transition=%u\n",
                 cases,noops,transitions);
}
"""
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 host compiler required"
with tempfile.TemporaryDirectory(prefix="encore-hle-suspend-noop-") as tmp:
    for name, method, noops in (("pinned", old, 1), ("native", new, 0)):
        src=Path(tmp)/(name+".cpp")
        exe=Path(tmp)/name
        src.write_text(CPP.replace("INJECT", method).replace("NOOP_STORES", str(noops)))
        subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=address,undefined",
                        "-fno-sanitize-recover=all", str(src), "-o", str(exe)],
                       check=True, timeout=90)
        subprocess.run([str(exe)], check=True, timeout=30)
print("NATIVE_HLE_SUSPEND_NOOP_HOST_PASS; PS5 gameplay/progress unmeasured")
