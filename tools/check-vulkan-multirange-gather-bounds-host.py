#!/usr/bin/env python3
"""Actual maintained GPU multi-range Get preflight, ASan/UBSan.

Validate that the sparse-fallback gathered path rejects invalid offsets and
sizes *before* buffer allocation/copy. Not a native GPU performance test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"vendor/encore-active/eden-vulkan/vk_multi_range_buffer_cost.cpp").read_text()
PIN=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_multi_range_buffer.cpp").read_text()
GEN=(ROOT/"tools/prepare-vulkan-port.py").read_text()
CI=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-vulkan-multirange-gather-bounds-host.py" in CI
assert "source.handle == VK_NULL_HANDLE" in SOURCE and "covered += source.size;" in GEN
method="MultiRangeRef MultiRangeBufferCache::Get("
start="    if (sources.empty() || total == 0) {"
end="    if (!retired.empty()) {"
assert SOURCE.count(method)==PIN.count(method)==1
after=SOURCE[SOURCE.index(method):]
baseline=PIN[PIN.index(method):]
assert after.index(start)<after.index(end)
preflight=after[after.index(start):after.index(end)]
assert "source.size > total - covered" in preflight
assert "source.offset > std::numeric_limits<VkDeviceSize>::max() - source.size" in preflight
assert "source.handle == VK_NULL_HANDLE" not in baseline[baseline.index(start):baseline.index(end)]
native_ref="return MultiRangeRef{};"
assert preflight.count(native_ref)==2
program=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <span>
using VkBuffer=std::uint64_t;
using VkDeviceSize=std::uint64_t;
constexpr VkBuffer VK_NULL_HANDLE=0;
struct MultiRangeSource {
    VkBuffer handle;
    VkDeviceSize offset;
    VkDeviceSize size;
};
bool Validate(std::span<const MultiRangeSource> sources,VkDeviceSize total) {
INJECT
    return true;
}
int main(){
    constexpr auto MAX=std::numeric_limits<VkDeviceSize>::max();
    std::array<MultiRangeSource,2> valid={{{17,0,64},{23,128,64}}};
    assert(Validate(valid,128));
    assert(Validate(valid,256)); // padding is legal
    assert(!Validate(valid,127));
    assert(!Validate(valid,0));
    assert(!Validate(std::span<const MultiRangeSource>{},128));
    auto bad=valid;
    bad[0].handle=0;assert(!Validate(bad,128));
    bad=valid;bad[0].size=0;assert(!Validate(bad,128));
    bad=valid;bad[0].size=MAX;assert(!Validate(bad,128));
    bad=valid;bad[0].offset=MAX-15;bad[0].size=64;
    assert(!Validate(bad,128));
    bad=valid;bad[0].offset=MAX-64;bad[0].size=64;
    assert(Validate(bad,128)); // exact upper edge does not overflow
    std::puts("ENCORE_MULTIRANGE_GATHER_INPUT_BOUNDS_PASS");
}
""".replace("INJECT",preflight.replace(native_ref,"return false;"))
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-multirange-gather-") as folder:
    f=Path(folder);p=f/"test.cpp";exe=f/"test";p.write_text(program)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(p),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("HOST_MULTIRANGE_GATHER_BOUNDS_PASS; PS5 frametimes unmeasured")
