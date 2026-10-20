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

root = Path(__file__).resolve().parents[3]
pinned = (root / "vendor/sources/eden/src/core/hle/kernel/k_condition_variable.cpp").read_text()
active = (root / "vendor/encore-active/eden-threading/src/core/hle/kernel/k_condition_variable.cpp").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
module = (root / "vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
assert "python3 -B tools/verify/hle/check-native-hle-condvar-key-host.py" in workflow
assert "native-hle-overrides.cmake" in cmake
assert "k_condition_variable.cpp" in module
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
old_write = """            // Write to the cv key.
            {
                constexpr u32 HasWaiterFlag = 1;
                WriteToUser(m_system.Kernel(), key, HasWaiterFlag);
"""
checked_write = """            // Publishing the waiter flag can fail even after address validation.
            // Do not enter a wait that cannot be signaled through guest memory.
            {
                constexpr u32 HasWaiterFlag = 1;
                if (!WriteToUser(m_system.Kernel(), key, HasWaiterFlag)) {
                    slp.CancelSleep();
                    R_THROW(ResultInvalidCurrentMemory);
                }
"""
expected_wait = wait(pinned).replace(anchor, guard + anchor)
assert expected_wait.count(old_write) == 1, "pinned CV waiter-flag write drift"
expected_wait = expected_wait.replace(old_write, checked_write)
# Publish before transferring the owner, so a failed flag write has no
# detached/runnable next owner while guest memory still names the old owner.
old_publication = checked_write + "                std::atomic_thread_fence(std::memory_order_seq_cst);\n            }\n\n"
new_publication = '        // Publish the waiter flag before relinquishing mutex ownership.\n        // A failed write must not detach or wake the next mutex owner.\n        {\n            constexpr u32 HasWaiterFlag = 1;\n            if (!WriteToUser(m_system.Kernel(), key, HasWaiterFlag)) {\n                slp.CancelSleep();\n                R_THROW(ResultInvalidCurrentMemory);\n            }\n            std::atomic_thread_fence(std::memory_order_seq_cst);\n        }\n\n'
assert expected_wait.count(old_publication) == 1
expected_wait = expected_wait.replace(old_publication, "")
expected_wait = expected_wait.replace(anchor, new_publication + anchor)
assert wait(active) == expected_wait

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
namespace Svc { constexpr u32 HandleWaitMask = 0x80000000U; }
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
    bool lose_key_mapping{};
    mutable int key_validations{};
    u32 mutex_word{9};
    u32 key_word{};
    bool IsValidVirtualAddressRange(KProcessAddress addr, u64 size) const {
        if (addr == 0x2000 && lose_key_mapping && ++key_validations > 1) {
            return false;
        }
        return size == sizeof(u32) && (addr == 0x1000 || addr == 0x2000);
    }
    void Write32(u64 addr, u32 word) {
        ++writes;
        if (addr == 0x1000) mutex_word = word;
        else if (addr == 0x2000 && !lose_key_mapping) key_word = word;
    }
};
struct KernelCore {
    Memory memory;
    KThread* current{};
    int cancelled_sleeps{};
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
    KernelCore& kernel;
    KScopedSchedulerLockAndSleep(KernelCore& k, KHardwareTimer** t, KThread*, s64)
        : kernel(k) { *t = nullptr; }
    void CancelSleep() { ++kernel.cancelled_sleeps; }
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
        assert(kernel.cancelled_sleeps == 1);
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
        assert(kernel.cancelled_sleeps == 0);
    }
    {
        // The initial key check succeeds, but WriteToUser's check fails.
        // Exercise the whole Wait method, including its later sleep/tree steps.
        KernelCore kernel;
        kernel.memory.lose_key_mapping = true;
        Core::System sys{kernel};
        KConditionVariable cv{sys};
        KThread waiting, next_owner;
        waiting.next_owner = &next_owner;
        kernel.current = &waiting;
        const auto result = cv.Wait(0x1000, 0x2000, 17, -1);
        assert(kernel.memory.key_word == 0);
#if EXPECT_FIXED
        assert(result == ResultInvalidCurrentMemory);
        assert(waiting.handoffs == 0 && next_owner.wakes == 0);
        assert(kernel.memory.key_validations == 2);
        assert(kernel.cancelled_sleeps == 1);
        assert(waiting.begin_waits == 0 && waiting.set_condvar == 0);
        assert(cv.m_tree.inserts == 0 && kernel.memory.writes == 0);
#else
        assert(result == ResultSuccess);
        assert(waiting.handoffs == 1 && next_owner.wakes == 1);
        assert(kernel.cancelled_sleeps == 0);
        assert(waiting.begin_waits == 1 && waiting.set_condvar == 1);
        assert(cv.m_tree.inserts == 1 && kernel.memory.writes == 2);
#endif
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
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        "-DEXPECT_FIXED=" + str(int(fixed)), str(cpp), "-o", str(exe)],
                       check=True, timeout=30)
        result = subprocess.run([str(exe)], capture_output=True, text=True, check=True, timeout=10)
        print(result.stdout, end="")
print("CV_KEY_GUEST_WAIT_HOST_WITNESS_ONLY_NO_CONSOLE_PROOF")
