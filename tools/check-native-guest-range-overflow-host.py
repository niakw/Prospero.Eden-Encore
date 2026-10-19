#!/usr/bin/env python3
"""Compile pinned Memory::IsValidVirtualAddressRange before/after native CMake guard.

Shows a wraparound false-positive in the original 64-bit range scan.
Host-only scope: no device, no guest mapping changes, no GPU/JIT barrier.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = root / "vendor/sources/eden/src/core/memory.cpp"
helper = root / "tools/fixtures/legacy-native-guest-range-overflow.cmake"
main_cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert 'include("${EDEN_PORT_DIR}/native_guest_range_overflow.cmake")' not in main_cmake
assert 'set(EDEN_NATIVE_GUEST_SOURCE "${EDEN_NATIVE_MEMORY_ROOT}/memory_native_standard.cpp")' in main_cmake
assert "python3 -B tools/check-native-guest-range-overflow-host.py" in workflow
assert pinned.read_text().count("Common::ProcessAddress end = base + size;") == 1
assert helper.read_text().count("std::numeric_limits<u64>::max() - GetInteger(base)") == 1
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler and shutil.which("cmake")


def real_method(source):
    start = "bool Memory::IsValidVirtualAddressRange(Common::ProcessAddress base, u64 size) const {"
    stop = "\nu8* Memory::GetPointer("
    assert source.count(start) == source.count(stop) == 1
    return start + source.split(start, 1)[1].split(stop, 1)[0].strip("\n") + "\n"


prelude = r"""
#include <cstdint>
#include <cstddef>
#include <limits>
#include <cassert>
#include <iostream>
using u8 = std::uint8_t;
using u64 = std::uint64_t;
inline constexpr unsigned YUZU_PAGEBITS = 12;
inline constexpr u64 YUZU_PAGESIZE = 4096;
namespace Common {
using ProcessAddress = u64;
u64 AlignDown(u64 number, u64 alignment) {
    return number & ~(alignment - 1);
}
}
u64 GetInteger(Common::ProcessAddress address) { return address; }
namespace Core::Memory {
struct Memory {
    bool IsValidVirtualAddress(Common::ProcessAddress address) const {
        return address < 0x10000;
    }
    bool IsValidVirtualAddressRange(Common::ProcessAddress base, u64 size) const;
};
"""
postlude = r"""
} // namespace Core::Memory
int main() {
    Core::Memory::Memory memory;
    constexpr u64 base = std::numeric_limits<u64>::max() - 8;
    // The original wraps end below the beginning and scans zero pages.
#if EXPECT_FIXED
    assert(!memory.IsValidVirtualAddressRange(base, 32));
#else
    assert(memory.IsValidVirtualAddressRange(base, 32));
#endif
    assert(memory.IsValidVirtualAddressRange(0x2000, 0x100));
    assert(memory.IsValidVirtualAddressRange(0x1000, 0x1000));
    assert(!memory.IsValidVirtualAddressRange(0xFF00, 0x200));
    assert(memory.IsValidVirtualAddressRange(0, 0));
    std::cout << (EXPECT_FIXED
        ? "PINNED_NATIVE_GUEST_RANGE_OVERFLOW_REJECTED_PASS\n"
        : "PINNED_GUEST_RANGE_OVERFLOW_FALSE_POSITIVE_WITNESS_PASS\n");
}
"""
with tempfile.TemporaryDirectory(prefix="encore-native-range-") as temp:
    folder = Path(temp)
    derived_path = folder / "derived.cpp"
    cmake_script = folder / "derive.cmake"
    cmake_script.write_text(
        f'file(READ "{pinned.as_posix()}" eden_cpu_memory)\n'
        f'include("{helper.as_posix()}")\n'
        f'file(WRITE "{derived_path.as_posix()}" "${{eden_cpu_memory}}")\n'
    )
    subprocess.run(["cmake", "-P", str(cmake_script)], check=True, timeout=20)
    original_source = pinned.read_text()
    derived_source = derived_path.read_text()
    maintained = (root/"vendor/encore-active/eden-core/src/core/memory_native_standard.cpp").read_text()
    assert real_method(maintained) == real_method(derived_source)
    assert derived_source.count("std::numeric_limits<u64>::max() - GetInteger(base)") == 1
    assert original_source.count("std::numeric_limits<u64>::max() - GetInteger(base)") == 0
    for name, src, fixed in (
        ("pinned", original_source, False),
        ("derived", derived_source, True),
    ):
        cpp = folder / f"{name}.cpp"
        exe = folder / name
        cpp.write_text(prelude + real_method(src) + postlude)
        subprocess.run(
            [compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
             "-DEXPECT_FIXED=" + str(int(fixed)), str(cpp), "-o", str(exe)],
            check=True, timeout=30,
        )
        run = subprocess.run([str(exe)], capture_output=True, check=True, text=True,
                             timeout=10)
        print(run.stdout, end="")
print("PINNED_GUEST_RANGE_NATIVE_ONLY_NO_GAME_CLAIM")
