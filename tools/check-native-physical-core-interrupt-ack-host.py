#!/usr/bin/env python3
"""Compile pinned PhysicalCore::RunThread / Interrupt / ClearInterrupt.

Deterministic host-only fake JIT shows that SignalInterrupt requests a
break but does not acknowledge ExitContext, and ClearInterrupt permits
another native RunThread admission with no tracked-page epoch guard.
NO native runtime hook, device fence, or #187 activation is implemented.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
read = lambda path: (root / path).read_text()
source = read("vendor/sources/eden/src/core/hle/kernel/physical_core.cpp")
a32 = read("vendor/sources/eden/src/core/arm/dynarmic/arm_dynarmic_32.cpp")
a64 = read("vendor/sources/eden/src/core/arm/dynarmic/arm_dynarmic_64.cpp")
cpu = read("vendor/sources/eden/src/core/cpu_manager.cpp")
replay = read("headless/gpu_deferred_replay.h")
workflow = read(".github/workflows/encore-core-preflight.yml")

def extract(start, finish):
    assert source.count(start) == 1 and source.count(finish) == 1
    return start + source.split(start, 1)[1].split(finish, 1)[0]

run = extract("void PhysicalCore::RunThread(KernelCore& kernel, Kernel::KThread* thread) {",
              "\nvoid PhysicalCore::LoadContext(")
interrupt = extract("void PhysicalCore::Interrupt() {",
                    "\nvoid PhysicalCore::ClearInterrupt() {")
clear = extract("void PhysicalCore::ClearInterrupt() {",
                "\n} // namespace Kernel")
for marker in ("const auto EnterContext = [&]() {", "const auto ExitContext = [&]() {",
               "std::scoped_lock lk{m_guard};", "interface->LockThread(thread);",
               "interface->UnlockThread(thread);", "m_arm_interface = nullptr;",
               "hr = interface->RunThread(thread);"):
    assert marker in run, marker
assert "arm_interface->SignalInterrupt(thread);" in interrupt
assert "m_is_interrupted = true;" in interrupt
assert "m_is_interrupted = false;" in clear
assert "while (!physical_core->IsInterrupted())" in cpu
assert all("m_jit->HaltExecution(BreakLoop);" in jit for jit in (a32, a64))
assert "inline constexpr bool kNativePostStorePublicationReady = false;" in replay
assert "python3 -B tools/check-native-physical-core-interrupt-ack-host.py" in workflow

prelude = r"""
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <semaphore>
#include <thread>
namespace Kernel { class KThread; class KProcess; class KernelCore; }
namespace Core {
enum class HaltReason : unsigned {
    StepThread=1, SupervisorCall=2, PrefetchAbort=4,
    InstructionBreakpoint=8, DataAbort=16, BreakLoop=32
};
constexpr HaltReason operator&(HaltReason x, HaltReason y) {
    return static_cast<HaltReason>(static_cast<unsigned>(x)&static_cast<unsigned>(y));
}
struct Debugger {
    void NotifyThreadStopped(Kernel::KThread*) {}
    void NotifyThreadWatchpoint(Kernel::KThread*, int) {}
};
struct System {
    Debugger debugger;
    bool DebuggerEnabled() const { return false; }
    Debugger& GetDebugger() { return debugger; }
};
class ArmInterface {
public:
    std::binary_semaphore entered{0}, release_run{0};
    std::atomic<unsigned> runs{0}, signals{0}, unlocks{0};
    int watchpoint=0;
    void Initialize() {}
    void LockThread(Kernel::KThread*) {}
    void UnlockThread(Kernel::KThread*) { ++unlocks; }
    HaltReason RunThread(Kernel::KThread*) {
        ++runs;
        entered.release();
        release_run.acquire();
        return HaltReason::BreakLoop;
    }
    HaltReason StepThread(Kernel::KThread*) { return HaltReason::StepThread; }
    void SignalInterrupt(Kernel::KThread*) { ++signals; }
    void GetContext(std::uint64_t&) {}
    void RewindBreakpointInstruction() {}
    void LogBacktrace(Kernel::KProcess*) {}
    int* HaltedWatchpoint() { return &watchpoint; }
    unsigned GetSvcNumber() const { return 0; }
};
}
constexpr bool True(Core::HaltReason reason) {
    return static_cast<unsigned>(reason) != 0;
}
namespace Kernel {
enum class StepState { None, StepPending, StepPerformed };
enum class SuspendType { Debug };
class KProcess {
public:
    explicit KProcess(Core::ArmInterface& arm): interface(&arm) {}
    Core::ArmInterface* GetArmInterface(std::size_t) { return interface; }
private:
    Core::ArmInterface* interface;
};
class KThread {
public:
    explicit KThread(KProcess& p) : process(&p) {}
    KProcess* GetOwnerProcess() { return process; }
    bool HasDpc() const { return false; }
    bool IsTerminationRequested() const { return false; }
    void Exit(KernelCore&) { std::abort(); }
    StepState GetStepState() const { return state; }
    void SetStepState(StepState v) { state=v; }
    void RequestSuspend(KernelCore&, SuspendType) {}
    std::uint64_t& GetContext() { return context; }
private:
    KProcess* process;
    StepState state{StepState::None};
    std::uint64_t context{};
};
class KernelCore {
public:
    explicit KernelCore(Core::System& s) : sys(s) {}
    Core::System& System() { return sys; }
private:
    Core::System& sys;
};
namespace Svc {
void Call(Core::System&, unsigned) {}
}
class PhysicalCore {
public:
    void RunThread(KernelCore&, KThread*);
    void Interrupt();
    void ClearInterrupt();
private:
    std::size_t m_core_index=0;
    std::mutex m_guard;
    std::condition_variable m_on_interrupt;
    Core::ArmInterface* m_arm_interface{};
    KThread* m_current_thread{};
    bool m_is_interrupted=false;
    bool m_is_single_core=false;
};
"""
postlude = r"""
} // namespace Kernel
int main() {
    Core::System system;
    Core::ArmInterface arm;
    Kernel::KernelCore kernel(system);
    Kernel::KProcess process(arm);
    Kernel::KThread thread(process);
    Kernel::PhysicalCore core;
    std::atomic<bool> returned{false};
    std::thread first([&] {
        core.RunThread(kernel, &thread);
        returned.store(true, std::memory_order_release);
    });
    arm.entered.acquire();
    assert(arm.runs == 1 && arm.unlocks == 0);
    core.Interrupt();
    assert(arm.signals == 1);
    assert(!returned.load(std::memory_order_acquire));
    assert(arm.unlocks == 0); // Requested != acknowledged EXIT.
    std::puts("PINNED_PHYSICAL_CORE_INTERRUPT_REQUEST_NOT_EXIT_ACK_PASS");
    arm.release_run.release();
    first.join();
    assert(returned.load(std::memory_order_acquire));
    assert(arm.unlocks == 1);
    // The persistent interrupt prevents immediate restart.
    core.RunThread(kernel, &thread);
    assert(arm.runs == 1);
    std::puts("PINNED_PHYSICAL_CORE_INTERRUPT_BLOCKS_REENTRY_PASS");
    // Clearing the interrupt alone now allows a new run. There is no
    // native page-transition generation or GPU first-use admission fence.
    core.ClearInterrupt();
    std::thread second([&] { core.RunThread(kernel, &thread); });
    arm.entered.acquire();
    assert(arm.runs == 2 && arm.unlocks == 1);
    core.Interrupt();
    arm.release_run.release();
    second.join();
    assert(arm.signals == 2 && arm.unlocks == 2);
    std::puts("PINNED_PHYSICAL_CORE_CLEAR_ALLOWS_NEW_RUN_PASS");
    std::puts("PINNED_PHYSICAL_CORE_NATIVE_HANDOFF_UNQUALIFIED");
}
"""
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler, "C++20 host compiler required"
with tempfile.TemporaryDirectory(prefix="encore-physical-core-") as tmp:
    code = Path(tmp) / "physical.cpp"
    binary = Path(tmp) / "physical"
    code.write_text(prelude + "\n" + run + "\n" + interrupt + "\n" + clear + "\n" + postlude)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra",
                    "-Werror", "-pthread", str(code), "-o", str(binary)],
                   check=True, timeout=30)
    result = subprocess.run([str(binary)], check=True, capture_output=True,
                            text=True, timeout=15)
    print(result.stdout, end="")
