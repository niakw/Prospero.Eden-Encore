#!/usr/bin/env python3
"""Host regression for native GPU IsGranularRange offset and bounds.

Compiles the pinned C++ method and the real CMake-derived body. The original
accepts a boundary-crossing continuous big-page span. No device/FPS claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
pinned = root / "vendor/sources/eden/src/video_core/memory_manager.cpp"
helper = root / "headless/native_gpu_granular_bounds.cmake"
cmake = (root / "headless/CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
assert 'include("${EDEN_PORT_DIR}/native_gpu_granular_bounds.cmake")' in cmake
assert "python3 -B tools/check-native-gpu-granular-bounds-host.py" in workflow
compiler = shutil.which("g++") or shutil.which("clang++")
assert compiler and shutil.which("cmake")

def method(source):
    start = "bool MemoryManager::IsGranularRange(GPUVAddr gpu_addr, std::size_t size) const {"
    end = "bool MemoryManager::IsContinuousRange("
    assert source.count(start) == source.count(end) == 1
    return start + source.split(start, 1)[1].split(end, 1)[0].rstrip() + "\n"

prelude = r"""
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <limits>
#include <iostream>
using u64 = std::uint64_t;
using GPUVAddr = u64;
namespace Core {
constexpr std::size_t DEVICE_PAGESIZE = 4096;
constexpr std::size_t DEVICE_PAGEMASK = DEVICE_PAGESIZE - 1;
}
class MemoryManager {
public:
    enum class EntryType { Free, Mapped };
    GPUVAddr address_space_size = 1ULL << 20;
    std::size_t big_page_bits = 16;
    std::size_t big_page_size = 1ULL << 16;
    std::size_t big_page_mask = (1ULL << 16) - 1;
    mutable int entry_checks = 0;
    bool big_mapped = true, short_mapped = true, continuous = true;
    EntryType GetEntry(GPUVAddr, bool is_big) const {
        ++entry_checks;
        return (is_big ? big_mapped : short_mapped) ? EntryType::Mapped : EntryType::Free;
    }
    bool IsBigPageContinuous(std::size_t) const { return continuous; }
    bool IsGranularRange(GPUVAddr gpu_addr, std::size_t size) const;
};
"""
tests = r"""
int main() {
    MemoryManager m;
    assert(m.IsGranularRange(0x10020, 32));
    assert(m.IsGranularRange(0x1FFE0, 32));
#if EXPECT_FIXED
    assert(!m.IsGranularRange(0x1FFF0, 32));
    assert(!m.IsGranularRange(0xFFFFF, 2));
    assert(!m.IsGranularRange(0x10000, std::numeric_limits<std::size_t>::max()));
    m.entry_checks = 0;
    assert(!m.IsGranularRange(1ULL << 20, 16));
    assert(m.entry_checks == 0);
    assert(!m.IsGranularRange(0x10000, 0));
#else
    assert(m.IsGranularRange(0x1FFF0, 32));
    assert(m.IsGranularRange(0xFFFFF, 2));
    assert(m.IsGranularRange(0x10000, std::numeric_limits<std::size_t>::max()));
#endif
    m.continuous = false;
    assert(!m.IsGranularRange(0x10FF0, 32));
    assert(m.IsGranularRange(0x10FE0, 32));
    m.big_mapped = false;
    assert(m.IsGranularRange(0x10FE0, 32));
    assert(!m.IsGranularRange(0x10FF0, 32));
    m.short_mapped = false;
    assert(!m.IsGranularRange(0x10020, 32));
    std::cout << (EXPECT_FIXED
        ? "PINNED_NATIVE_GPU_GRANULAR_SPAN_GUARD_PASS\n"
        : "PINNED_GPU_GRANULAR_BOUNDARY_FALSE_POSITIVE_WITNESS_PASS\n");
}
"""
with tempfile.TemporaryDirectory(prefix="encore-gpu-granularity-") as td:
    temp = Path(td)
    derivation = temp / "derive.cmake"
    derived = temp / "native.cpp"
    derivation.write_text(
        f'file(READ "{pinned.as_posix()}" eden_gpu_span_src)\n'
        f'include("{helper.as_posix()}")\n'
        f'file(WRITE "{derived.as_posix()}" "' + '$' + '{eden_gpu_span_src}' + '")\n'
    )
    subprocess.run(["cmake", "-P", str(derivation)], check=True, timeout=25)
    original = pinned.read_text()
    corrected = derived.read_text()
    assert "page_index & big_page_mask) + size" in original
    assert "page_index & big_page_mask) + size" not in corrected
    assert "big_page_size - (gpu_addr & big_page_mask)" in corrected
    for name, source, fixed in (
        ("pinned", original, False),
        ("native", corrected, True),
    ):
        cpp = temp / f"{name}.cpp"
        exe = temp / name
        cpp.write_text(prelude + method(source) + tests)
        subprocess.run(
            [compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
             "-DEXPECT_FIXED=" + str(int(fixed)), str(cpp), "-o", str(exe)],
            check=True, timeout=30,
        )
        run = subprocess.run([str(exe)], capture_output=True, text=True,
                             check=True, timeout=10)
        print(run.stdout, end="")
print("PINNED_GPU_GRANULAR_RANGE_HOST_ONLY_NO_DEVICE_PROOF")
