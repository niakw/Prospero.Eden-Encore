#!/usr/bin/env python3
"""Compile both real GPU GetSpan overloads with checked page-table range fixture.

The original methods access the range-walking page table before validating
GPU address-space bounds. The native derived methods must reject invalid
ranges first, without altering the normal valid-range lookup sequence.
This is host-only; no graphics driver or console environment is required.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "vendor/sources/eden/src/video_core/memory_manager.cpp").read_text()
cmake = (ROOT / "headless/CMakeLists.txt").read_text()
workflow = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()
start = "const u8* MemoryManager::GetSpan(const GPUVAddr src_addr, const std::size_t size) const {"
end = "} // namespace Tegra"
assert source.count(start) == 1 and source.count(end) == 1
methods = source[source.index(start):source.index(end)]
old = "    if (!IsContinuousRange(src_addr, size)) {"
assert methods.count(old) == 2
replacement_anchor = 'string(REPLACE "${eden_gpu_span_original}" [=['
assert cmake.count(replacement_anchor) == 1
native_start = cmake.index(replacement_anchor) + len(replacement_anchor)
native_end = cmake.index(']=] eden_gpu_span_src "${eden_gpu_span_src}")', native_start)
new = cmake[native_start:native_end]
assert 'size == 0 || src_addr >= address_space_size' in new
assert 'size > address_space_size - src_addr' in new
assert new.count('!IsContinuousRange(src_addr, size)') == 1
assert cmake.count('Pinned native GPU guest span range gate changed') == 1
assert cmake.count('list(REMOVE_ITEM video_sources "memory_manager.cpp")') == 1
assert cmake.count('list(APPEND video_sources "${eden_gpu_span_tu}")') == 1
assert "python3 -B tools/check-native-gpu-span-range-host.py" in workflow

cpp = r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <stdexcept>
using u8 = std::uint8_t;
using GPUVAddr = std::uint64_t;
using DAddr = std::uint64_t;
struct FakeDevice {
    std::array<u8,8192> bytes{};
    u8* GetSpan(DAddr a, std::size_t n) {
        return a < bytes.size() && n <= bytes.size() - a
            ? bytes.data() + a : nullptr;
    }
    const u8* GetSpan(DAddr a, std::size_t n) const {
        return a < bytes.size() && n <= bytes.size() - a
            ? bytes.data() + a : nullptr;
    }
};
struct MemoryManager {
    static constexpr GPUVAddr address_space_size = 8192;
    FakeDevice memory;
    mutable unsigned probes{};
    std::array<int,2> page_table{1,1};
    bool IsContinuousRange(GPUVAddr addr, std::size_t) const {
        ++probes;
        // Mirrors the unguarded GetEntry indexed page-vector access.
        return page_table.at(static_cast<std::size_t>(addr >> 12)) != 0;
    }
    std::optional<DAddr> GpuToCpuAddress(GPUVAddr addr) const {
        if (addr >= address_space_size) return std::nullopt;
        return addr;
    }
    const u8* GetSpan(GPUVAddr addr,std::size_t size) const;
    u8* GetSpan(GPUVAddr addr,std::size_t size);
};
@@METHODS@@
int main() {
    MemoryManager m;
    const auto& c=static_cast<const MemoryManager&>(m);
    assert(m.GetSpan(0,4096)!=nullptr);
    assert(c.GetSpan(4096,4096)!=nullptr);
    assert(m.GetSpan(4095,2)!=nullptr);
#ifdef EXPECT_NATIVE
    auto prior=m.probes;
    assert(m.GetSpan(8192,1)==nullptr);
    assert(c.GetSpan(8192,1)==nullptr);
    assert(m.GetSpan(0,0)==nullptr);
    assert(c.GetSpan(0,0)==nullptr);
    assert(m.GetSpan(8191,2)==nullptr);
    assert(c.GetSpan(8191,2)==nullptr);
    assert(m.GetSpan(UINT64_MAX,2)==nullptr);
    assert(c.GetSpan(UINT64_MAX,2)==nullptr);
    assert(m.probes == prior); // Never walk unmapped/out-of-space vectors.
#else
    bool threw=false;
    try { (void)m.GetSpan(8192,1); }
    catch(const std::out_of_range&) { threw=true; }
    assert(threw);  // Original calls the page walk with invalid page index.
    threw=false;
    try { (void)c.GetSpan(8192,1); }
    catch(const std::out_of_range&) { threw=true; }
    assert(threw);
    assert(m.GetSpan(0,0)!=nullptr); // Original silently accepts zero span.
#endif
}
"""
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 is required"
with tempfile.TemporaryDirectory(prefix="encore-gpu-span-range-") as scratch:
    dest=Path(scratch)
    for name,body,enabled in (("pinned",methods,False),
                              ("native",methods.replace(old,new),True)):
        unit=dest / (name + ".cpp")
        unit.write_text(cpp.replace("@@METHODS@@",body))
        exe=dest / name
        command=[clang,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                 "-fsanitize=address,undefined","-fno-sanitize-recover=all"]
        if enabled: command.append("-DEXPECT_NATIVE")
        command += [str(unit),"-o",str(exe)]
        subprocess.run(command,check=True,timeout=45)
        subprocess.run([str(exe)],check=True,timeout=45)
print("NATIVE_GPU_SPAN_RANGE_HOST_PASS original_oob_pagewalk=2 original_zero_span=1 native_const_mutable=2 native_zero=1 overflow=1 past_end=1 normal_ranges=3")
