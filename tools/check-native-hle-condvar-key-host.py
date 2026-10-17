#!/usr/bin/env python3
"""Execute the actual guest condition-variable Wait() against a mapped-key witness.

The pinned source silently proceeds to a guest wait when writing the condition
variable's waiter flag fails. The native source refuses the bad key *before*
transferring mutex ownership. Host-only test; no device or freeze proof.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = (root / "vendor/sources/eden/src/core/hle/kernel/k_condition_variable.cpp").read_text()
active = (root / "vendor/encore-active/eden-threading/src/core/hle/kernel/k_condition_variable.cpp").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
assert "python3 -B tools/check-native-hle-condvar-key-host.py" in workflow
assert 'list(APPEND eden_cv_core_sources "${eden_active_cv}")' in cmake
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler

def helper(source):
    start = "bool WriteToUser(KernelCore& kernel, KProcessAddress address, u32 val) {"
    end = "bool UpdateLockAtomic(KernelCore& kernel,"
    assert source.count(start) == source.count(end) == 1
    return start + source.split(start, 1)[1].split(end, 1)[0].strip() + "\n"

def wait(source):
    start = "Result KConditionVariable::Wait(KProcessAddress addr, u64 key, u32 value, s64 timeout) {"
    end = "} // namespace Kernel"
    assert source.count(start) == source.count(end) == 1
    return start + source.split(start, 1)[1].split(end, 1)[0].strip() + "\n"

guard = """        // A missing condition-variable key cannot publish the waiter flag.
        // Reject it before handing off the guest mutex or entering a wait.
        if (!GetCurrentMemory(m_system.Kernel()).IsValidVirtualAddressRange(key, sizeof(u32))) {
            slp.CancelSleep();
            R_THROW(ResultInvalidCurrentMemory);
        }

"""
anchor = "        // Update the value and process for the next owner.\n"
assert pinned.count(anchor) == active.count(anchor) == 1
assert active.count(guard) == 1
assert guard not in pinned
assert wait(active) == wait(pinned).replace(anchor, guard + anchor)

prelude = r"""
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <memory>
#include <iostream>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s32 = std::int32_t;
using s64 = std::int64_t;
namespace Kernel {
using KProcessAddress = u64;
using Result = int;
constexpr Result ResultSuccess = 0;
constexpr Result ResultInvalidCurrentMemory = 1;
constexpr Result ResultTerminationRequested = 2;
constexpr Result ResultTimedOut = 3;
#define R_THROW(r) return (r)
#define R_UNLESS(condition, r) do { if (!(condition)) return (r); } while (0)
#define R_RETURN(r) return (r)
struct KThread;
struct ThreadTree {
    int inserts{};
    void insert(KThread&) { ++inserts; }
};
struct Memory {
    int writes{};
    u32 mutex_word{9};
    u32 key_word{};
    bool IsValidVirtualAddressRange(KProcessAddress addr, u64 size) const {
        return size == sizeof(u32) && (addr == 0x1000 || addr == 0x2000);
    }
    void Write32(u64 addr, u32 word) {
        ++writes;
        if (addr == 0x1000) mutex_word = word;
        else if (addr == 0x2000) key_word = word;
    }
};
struct KernelCore {
    Memory memory;
    KThread* current{};
};
struct KHardwareTimer {};
struct KThread {
    bool terminate{};
    int handoffs{};
    int wakes{};
    int begin_waits{};
    int set_condvar{};
    KThread* next_owner{};
    bool IsTerminationRequested() const { return terminate; }
    KThread* RemoveUserWaiterByKey(KernelCore&, bool* has_waiters, KProcessAddress) {
        ++handoffs;
        *has_waiters = false;
        return next_owner;
    }
    u32 GetAddressKeyValue() const { return 17; }
    void EndWait(KernelCore&, Result) { ++wakes; }
    void SetConditionVariable(ThreadTree*, KProcessAddress, u64, u32) { ++set_condvar; }
    void BeginWait(KernelCore&, void*) { ++begin_waits; }
    void SetWaitReasonForDebugging(int) {}
    Result GetWaitResult() const { return ResultSuccess; }
};
struct ThreadWaitReasonForDebugging { static constexpr int ConditionVar = 1; };
KThread* GetCurrentThreadPointer(KernelCore& kernel) { return kernel.current; }
Memory& GetCurrentMemory(KernelCore& kernel) { return kernel.memory; }
u64 GetInteger(KProcessAddress address) { return address; }
struct ThreadQueueImplForKConditionVariableWaitConditionVariable {
    ThreadQueueImplForKConditionVariableWaitConditionVariable(KernelCore&, ThreadTree*) {}
    void SetHardwareTimer(KHardwareTimer*) {}
};
struct KScopedSchedulerLockAndSleep {
    KScopedSchedulerLockAndSleep(KernelCore&, KHardwareTimer** t, KThread*, s64) { *t = nullptr; }
    void CancelSleep() {}
};
} // namespace Kernel
namespace Core {
struct System {
    Kernel::KernelCore& kernel;
    Kernel::KernelCore& Kernel() { return kernel; }
};
}
namespace Kernel {
struct KConditionVariable {
    Core::System& m_system;
    ThreadTree m_tree;
    explicit KConditionVariable(Core::System& s) : m_system(s) {}
    Result Wait(KProcessAddress addr, u64 key, u32 value, s64 timeout);
};
namespace {
"""
middle = r"""
} // anonymous namespace
"""
postlude = r"""
} // namespace Kernel
int main() {
    using namespace Kernel;
    {
        KernelCore kernel;
        Core::System sys{kernel};
        KConditionVariable cv{sys};
        KThread waiting, next_owner;
        waiting.next_owner = &next_owner;
        kernel.current = &waiting;
        const auto result = cv.Wait(0x1000, 0x3000, 17, -1);
#if EXPECT_FIXED
        assert(result == ResultInvalidCurrentMemory);
        assert(waiting.handoffs == 0 && next_owner.wakes == 0);
        assert(waiting.begin_waits == 0 && waiting.set_condvar == 0);
        assert(cv.m_tree.inserts == 0 && kernel.memory.writes == 0);
#else
        // Pinned implementation erroneously claims a successful blocked wait
        // even though the missing cv key never receives HasWaiterFlag.
        assert(result == ResultSuccess);
        assert(waiting.handoffs == 1 && next_owner.wakes == 1);
        assert(waiting.begin_waits == 1 && cv.m_tree.inserts == 1);
        assert(kernel.memory.writes == 2 && kernel.memory.key_word == 0);
#endif
    }
    {
        KernelCore kernel;
        Core::System sys{kernel};
        KConditionVariable cv{sys};
        KThread waiting, next_owner;
        waiting.next_owner = &next_owner;
        kernel.current = &waiting;
        const auto result = cv.Wait(0x1000, 0x2000, 17, -1);
        assert(result == ResultSuccess);
        assert(waiting.handoffs == 1 && next_owner.wakes == 1);
        assert(waiting.begin_waits == 1 && waiting.set_condvar == 1);
        assert(cv.m_tree.inserts == 1);
        assert(kernel.memory.writes == 2);
        assert(kernel.memory.key_word == 1 && kernel.memory.mutex_word == 17);
    }
    std::cout << (EXPECT_FIXED ? "NATIVE_CV_KEY_INVALID_ACCESS_REJECTED_PASS\n"
                               : "PINNED_CV_KEY_LOST_WAIT_WITNESS_PASS\n");
}
"""
with tempfile.TemporaryDirectory(prefix="encore-cv-key-") as td:
    temp = Path(td)
    for label, text, fixed in (("pinned", pinned, False), ("native", active, True)):
        cpp, exe = temp / f"{label}.cpp", temp / label
        cpp.write_text(prelude + helper(text) + middle + wait(text) + postlude)
        subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-DEXPECT_FIXED=" + str(int(fixed)), str(cpp), "-o", str(exe)],
                       check=True, timeout=30)
        result = subprocess.run([str(exe)], capture_output=True, text=True, check=True, timeout=10)
        print(result.stdout, end="")
print("CV_KEY_GUEST_WAIT_HOST_WITNESS_ONLY_NO_CONSOLE_PROOF")
