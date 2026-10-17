#!/usr/bin/env python3
"""Host witness for unmapped guest addresses in native address arbitration.

Compiles the exact pinned and maintained helper bodies using a memory facade
with the original missing-pointer no-op/write-success semantics. Verifies
valid operations are unchanged; no console, scheduling or freeze claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned_path = root / "vendor/sources/eden/src/core/hle/kernel/k_address_arbiter.cpp"
active_path = root / "vendor/encore-active/eden-threading/src/core/hle/kernel/k_address_arbiter.cpp"
cmake = (root / "headless/CMakeLists.txt").read_text()
module = (root / "vendor/encore-active/eden-threading/native-hle-overrides.cmake").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-native-hle-arbiter-access-host.py" in workflow
assert "native-hle-overrides.cmake" in cmake
assert "k_address_arbiter.cpp" in module
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler

def real_helpers(source):
    start = "bool ReadFromUser(KernelCore& kernel, s32* out, KProcessAddress address) {"
    stop = "class ThreadQueueImplForKAddressArbiter"
    assert source.count(start) == source.count(stop) == 1
    return start + source.split(start, 1)[1].split(stop, 1)[0].strip() + "\n"

prelude = r"""
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <iostream>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s32 = std::int32_t;
namespace Kernel {
using KProcessAddress = u64;
struct Memory {
    s32 word{5};
    int reads{};
    int writes{};
    bool IsValidVirtualAddressRange(KProcessAddress addr, u64 size) const {
        return addr == 0x1000 && size == sizeof(s32);
    }
    u32 Read32(u64 addr) {
        ++reads;
        return IsValidVirtualAddressRange(addr, 4) ? static_cast<u32>(word) : 0;
    }
    void Write32(u64 addr, u32 value) {
        ++writes;
        if (IsValidVirtualAddressRange(addr, 4)) word = static_cast<s32>(value);
    }
};
struct Monitor {
    Memory* memory{};
    int writes{};
    int clears{};
    u32 ExclusiveRead32(std::size_t, u64 addr) { return memory->Read32(addr); }
    bool ExclusiveWrite32(std::size_t, u64 addr, u32 value) {
        ++writes;
        memory->Write32(addr, value);
        // Pinned Memory::WriteExclusive reports success for an unmapped pointer.
        return true;
    }
    void ClearExclusive(std::size_t) { ++clears; }
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
} // namespace anonymous
} // namespace Kernel
int main() {
    using namespace Kernel;
    KernelCore kernel;
    s32 out = 999;
    assert(ReadFromUser(kernel, &out, 0x1000));
    assert(out == 5);
    assert(DecrementIfLessThan(kernel, &out, 0x1000, 10));
    assert(out == 5 && kernel.memory.word == 4);
    assert(UpdateIfEqual(kernel, &out, 0x1000, 4, 7));
    assert(out == 4 && kernel.memory.word == 7);
    // A mapped address with a failed comparison must not be modified.
    const int prior_exclusive = kernel.process.monitor.writes;
    assert(UpdateIfEqual(kernel, &out, 0x1000, 3, 99));
    assert(out == 7 && kernel.memory.word == 7);
    assert(kernel.process.monitor.writes == prior_exclusive);
    [[maybe_unused]] const int before_reads = kernel.memory.reads;
    [[maybe_unused]] const int before_writes = kernel.memory.writes;
    [[maybe_unused]] const int before_exclusive = kernel.process.monitor.writes;
    out = 123;
#if EXPECT_FIXED
    assert(!ReadFromUser(kernel, &out, 0x3000));
    assert(!DecrementIfLessThan(kernel, &out, 0x3000, 10));
    assert(!UpdateIfEqual(kernel, &out, 0x3000, 0, 9));
    assert(kernel.memory.reads == before_reads);
    assert(kernel.memory.writes == before_writes);
    assert(kernel.process.monitor.writes == before_exclusive);
    assert(out == 123);
#else
    assert(ReadFromUser(kernel, &out, 0x3000));
    assert(out == 0);
    assert(DecrementIfLessThan(kernel, &out, 0x3000, 10));
    assert(UpdateIfEqual(kernel, &out, 0x3000, 0, 9));
    assert(kernel.process.monitor.writes == before_exclusive + 2);
#endif
    assert(kernel.memory.word == 7);
    std::cout << (EXPECT_FIXED
        ? "NATIVE_ARBITER_INVALID_ADDRESS_REJECTION_PASS\n"
        : "PINNED_ARBITER_FALSE_SUCCESS_WITNESS_PASS\n");
}
"""
pinned = pinned_path.read_text()
active = active_path.read_text()
expected = pinned
guard = ("    if (!GetCurrentMemory(kernel).IsValidVirtualAddressRange(address, sizeof(s32))) {\n"
         "        return false;\n"
         "    }\n")
anchors = [
    "bool ReadFromUser(KernelCore& kernel, s32* out, KProcessAddress address) {\n",
    "bool DecrementIfLessThan(KernelCore& kernel, s32* out, KProcessAddress address, s32 value) {\n",
    "bool UpdateIfEqual(KernelCore& kernel, s32* out, KProcessAddress address, s32 value,\n                   s32 new_value) {\n",
]
for anchor in anchors:
    assert expected.count(anchor) == 1, "pinned arbiter contract drift"
    expected = expected.replace(anchor, anchor + guard)
# Boundary arithmetic must retain the 32-bit guest word's modulo behavior
# without invoking C++ signed-overflow UB in native builds.
wrap_replacements = [
    ("const s32 decrement_value = current_value - 1;",
     "const s32 decrement_value = static_cast<s32>(static_cast<u32>(current_value) - 1u);", 1),
    ("std::addressof(user_value), addr, value, value + 1)",
     "std::addressof(user_value), addr, value,\n"
     "                                static_cast<s32>(static_cast<u32>(value) + 1u))", 1),
    ("new_value = value - 2;",
     "new_value = static_cast<s32>(static_cast<u32>(value) - 2u);", 1),
    ("new_value = value - 1;",
     "new_value = static_cast<s32>(static_cast<u32>(value) - 1u);", 1),
    ("new_value = value + 1;",
     "new_value = static_cast<s32>(static_cast<u32>(value) + 1u);", 2),
]
for old, new, count in wrap_replacements:
    assert expected.count(old) == count, "pinned arithmetic contract drift"
    expected = expected.replace(old, new)
assert active == expected, "native arbiter differs from pinned + three guards"
with tempfile.TemporaryDirectory(prefix="encore-arbiter-access-") as td:
    temp = Path(td)
    for name, content, fixed in (("pinned", pinned, False), ("native", active, True)):
        cpp, exe = temp / f"{name}.cpp", temp / name
        cpp.write_text(prelude + real_helpers(content) + postlude)
        subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-DEXPECT_FIXED=" + str(int(fixed)), str(cpp), "-o", str(exe)],
                       check=True, timeout=30)
        out = subprocess.run([str(exe)], capture_output=True, text=True, check=True, timeout=10)
        print(out.stdout, end="")
print("NATIVE_ARBITER_GUARD_HOST_ONLY_NO_CONSOLE_PROOF")
