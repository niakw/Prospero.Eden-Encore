#!/usr/bin/env python3
"""C++ host witness: fail invalid guest-memory condition-variable accesses.

Execute exact pinned and CMake-derived helpers with mapped and unmapped mock
memory, reproducing the memory facade's no-op write/zero-read semantics.
No console, frame progression, or deadlock claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = root / "vendor/sources/eden/src/core/hle/kernel/k_condition_variable.cpp"
helper = root / "headless/native_hle_condvar_access.cmake"
cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert 'include("${EDEN_PORT_DIR}/native_hle_condvar_access.cmake")' in cmake
assert "python3 -B tools/check-native-hle-condvar-access-host.py" in workflow
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler and shutil.which("cmake")

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
with tempfile.TemporaryDirectory(prefix="encore-condvar-access-") as td:
    temp = Path(td)
    derivation = temp / "derive.cmake"
    derived = temp / "native.cpp"
    derivation.write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        f'file(READ "{pinned.as_posix()}" eden_cv_source)\n'
        f'include("{helper.as_posix()}")\n'
        f'file(WRITE "{derived.as_posix()}" "' + '$' + '{eden_cv_source}' + '")\n'
    )
    subprocess.run(["cmake", "-P", str(derivation)], check=True, timeout=25)
    original = pinned.read_text()
    corrected = derived.read_text()
    assert "        can_access = true;" in original
    assert "        can_access = true;" not in corrected
    assert "        can_access = UpdateLockAtomic(kernel," in corrected
    for name, source, fixed in (("pinned", original, False), ("native", corrected, True)):
        cpp, exe = temp / f"{name}.cpp", temp / name
        cpp.write_text(prelude + real_helpers(source) + postlude)
        subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-DEXPECT_FIXED=" + str(int(fixed)), str(cpp), "-o", str(exe)],
                       check=True, timeout=30)
        result = subprocess.run([str(exe)], capture_output=True, text=True, check=True, timeout=10)
        print(result.stdout, end="")
print("NATIVE_CONDVAR_GUARD_HOST_ONLY_NO_CONSOLE_PROOF")
