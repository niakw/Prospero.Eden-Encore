#!/usr/bin/env python3
"""C++ host witness: fail invalid guest-memory condition-variable accesses.

Execute exact pinned and maintained native helpers with mapped and unmapped mock
memory, reproducing the memory facade's no-op write/zero-read semantics.
No console, frame progression, or deadlock claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
pinned = root / "vendor/sources/eden/src/core/hle/kernel/k_condition_variable.cpp"
active = root / "vendor/encore-active/eden-threading/src/core/hle/kernel/k_condition_variable.cpp"
cmake = (root / "headless/CMakeLists.txt").read_text()
module = (root / "vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/verify/hle/check-native-hle-condvar-access-host.py" in workflow
assert "native-hle-overrides.cmake" in cmake
assert "k_condition_variable.cpp" in module
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler

def real_helpers(source):
    start = "bool ReadFromUser(KernelCore& kernel, u32* out, KProcessAddress address) {"
    stop = "class ThreadQueueImplForKConditionVariableWaitForAddress"
    assert source.count(start) == source.count(stop) == 1
    return start + source.split(start, 1)[1].split(stop, 1)[0].strip() + "\n"

prelude = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
namespace Kernel {
using KProcessAddress = u64;
struct Memory {
    u32 word{5};
    int reads{};
    int writes{};
    bool IsValidVirtualAddressRange(KProcessAddress addr, u64 size) const {
        return addr == 0x1000 && size == 4;
    }
    u32 Read32(u64 addr) {
        ++reads;
        return IsValidVirtualAddressRange(addr, 4) ? word : 0;
    }
    void Write32(u64 addr, u32 value) {
        ++writes;
        if (IsValidVirtualAddressRange(addr, 4)) word = value;
    }
};
struct Monitor {
    Memory* memory{};
    int writes{};
    u32 ExclusiveRead32(std::size_t, u64 addr) { return memory->Read32(addr); }
    bool ExclusiveWrite32(std::size_t, u64 addr, u32 value) {
        ++writes;
        memory->Write32(addr, value);
        // Pinned Memory::WriteExclusive returns true when no pointer exists.
        return true;
    }
};
struct Process {
    Monitor monitor;
    Monitor& GetExclusiveMonitor() { return monitor; }
};
struct KernelCore {
    Memory memory;
    Process process;
    KernelCore() { process.monitor.memory = &memory; }
    std::size_t CurrentPhysicalCoreIndex() const { return 0; }
};
Memory& GetCurrentMemory(KernelCore& k) { return k.memory; }
Process& GetCurrentProcess(KernelCore& k) { return k.process; }
u64 GetInteger(KProcessAddress addr) { return addr; }
namespace {
"""
postlude = r"""
} // anonymous namespace
} // namespace Kernel
int main() {
    using namespace Kernel;
    KernelCore kernel;
    u32 out = 999;
    assert(ReadFromUser(kernel, &out, 0x1000));
    assert(out == 5);
    assert(WriteToUser(kernel, 0x1000, 7));
    assert(kernel.memory.word == 7);
    u32 prev = 0;
    assert(UpdateLockAtomic(kernel, &prev, 0x1000, 11, 0x80000000U));
    assert(prev == 7 && kernel.memory.word == 0x80000007U);
    [[maybe_unused]] const int before_reads = kernel.memory.reads;
    [[maybe_unused]] const int before_writes = kernel.memory.writes;
    const int before_exclusive = kernel.process.monitor.writes;
    out = 123;
#if EXPECT_FIXED
    assert(!ReadFromUser(kernel, &out, 0x3000));
    assert(!WriteToUser(kernel, 0x3000, 9));
    assert(!UpdateLockAtomic(kernel, &prev, 0x3000, 11, 0x80000000U));
    assert(kernel.memory.reads == before_reads);
    assert(kernel.memory.writes == before_writes);
    assert(kernel.process.monitor.writes == before_exclusive);
    assert(out == 123);
#else
    assert(ReadFromUser(kernel, &out, 0x3000));
    assert(out == 0);
    assert(WriteToUser(kernel, 0x3000, 9));
    assert(UpdateLockAtomic(kernel, &prev, 0x3000, 11, 0x80000000U));
    assert(kernel.process.monitor.writes == before_exclusive + 1);
#endif
    assert(kernel.memory.word == 0x80000007U);
    std::cout << (EXPECT_FIXED
        ? "NATIVE_CONDVAR_INVALID_ADDRESS_REJECTION_PASS\n"
        : "PINNED_CONDVAR_FALSE_SUCCESS_WITNESS_PASS\n");
}
"""
original = pinned.read_text()
corrected = active.read_text()
# Reject accidental upstream drift or unrelated maintained-source edits.
expected = original
replacements = [["    *out = GetCurrentMemory(kernel).Read32(GetInteger(address));\n    return true;","    auto& memory = GetCurrentMemory(kernel);\n    if (!memory.IsValidVirtualAddressRange(address, sizeof(u32))) {\n        return false;\n    }\n    *out = memory.Read32(GetInteger(address));\n    return true;"],["    GetCurrentMemory(kernel).Write32(GetInteger(address), val);\n    return true;","    auto& memory = GetCurrentMemory(kernel);\n    if (!memory.IsValidVirtualAddressRange(address, sizeof(u32))) {\n        return false;\n    }\n    memory.Write32(GetInteger(address), val);\n    return true;"],["    auto& monitor = GetCurrentProcess(kernel).GetExclusiveMonitor();","    if (!GetCurrentMemory(kernel).IsValidVirtualAddressRange(address, sizeof(u32))) {\n        return false;\n    }\n    auto& monitor = GetCurrentProcess(kernel).GetExclusiveMonitor();"],["        can_access = true;\n        if (can_access) {\n            UpdateLockAtomic(kernel, std::addressof(prev_tag), address, own_tag, Svc::HandleWaitMask);\n        }","        can_access = UpdateLockAtomic(kernel, std::addressof(prev_tag), address,\n                                      own_tag, Svc::HandleWaitMask);"]]
for old, new in replacements:
    assert expected.count(old) == 1, "pinned native HLE patch drift"
    expected = expected.replace(old, new)
# H09 extends the maintained condition-variable source by one checked Wait guard.
wait_anchor = "        // Update the value and process for the next owner.\n"
wait_guard = ("        // A missing condition-variable key cannot publish the waiter flag.\n"
              "        // Reject it before handing off the guest mutex or entering a wait.\n"
              "        if (!GetCurrentMemory(m_system.Kernel()).IsValidVirtualAddressRange(key, sizeof(u32))) {\n"
              "            slp.CancelSleep();\n"
              "            R_THROW(ResultInvalidCurrentMemory);\n"
              "        }\n\n")
assert expected.count(wait_anchor) == 1
expected = expected.replace(wait_anchor, wait_guard + wait_anchor)
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
assert expected.count(old_write) == 1, "pinned CV waiter-flag write drift"
expected = expected.replace(old_write, checked_write)
# Publish before transferring the owner, so a failed flag write has no
# detached/runnable next owner while guest memory still names the old owner.
old_publication = checked_write + "                std::atomic_thread_fence(std::memory_order_seq_cst);\n            }\n\n"
new_publication = '        // Publish the waiter flag before relinquishing mutex ownership.\n        // A failed write must not detach or wake the next mutex owner.\n        {\n            constexpr u32 HasWaiterFlag = 1;\n            if (!WriteToUser(m_system.Kernel(), key, HasWaiterFlag)) {\n                slp.CancelSleep();\n                R_THROW(ResultInvalidCurrentMemory);\n            }\n            std::atomic_thread_fence(std::memory_order_seq_cst);\n        }\n\n'
assert expected.count(old_publication) == 1
expected = expected.replace(old_publication, "")
expected = expected.replace(wait_anchor, new_publication + wait_anchor)
assert corrected == expected, "maintained native HLE source differs from pinned + named fixes"
assert "        can_access = UpdateLockAtomic(kernel," in corrected
with tempfile.TemporaryDirectory(prefix="encore-condvar-access-") as td:
    temp = Path(td)
    for name, source, fixed in (("pinned", original, False), ("native", corrected, True)):
        cpp, exe = temp / f"{name}.cpp", temp / name
        cpp.write_text(prelude + real_helpers(source) + postlude)
        subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-DEXPECT_FIXED=" + str(int(fixed)), str(cpp), "-o", str(exe)],
                       check=True, timeout=30)
        result = subprocess.run([str(exe)], capture_output=True, text=True, check=True, timeout=10)
        print(result.stdout, end="")
print("NATIVE_CONDVAR_GUARD_HOST_ONLY_NO_CONSOLE_PROOF")
