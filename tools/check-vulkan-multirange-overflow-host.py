#!/usr/bin/env python3
"""Source-extracted ASan/UBSan regression for sparse Vulkan range arithmetic."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "vendor/encore-active/eden-vulkan/vk_multi_range_buffer_cost.cpp").read_text()
generator = (ROOT / "tools/prepare-vulkan-port.py").read_text()
workflow = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()
start = "bool MultiRangeBufferCache::CanBindSparse(std::span<const MultiRangeSource> sources) const {"
end = "\nSparseBuffer MultiRangeBufferCache::CreateSparse("
assert source.count(start) == 1
can = source[source.index(start):source.index(end, source.index(start))]
pre_start = "                                                 VkDeviceSize total) {"
pre_end = "    const VkDevice logical = *device.GetLogical();"
assert source.count(pre_start) == 1
pre = source[source.index(pre_start) + len(pre_start):source.index(pre_end, source.index(pre_start))]
assert pre.count("return SparseBuffer{};") == 2
assert "std::numeric_limits<VkDeviceSize>::max()" in can and "checked_total" in pre
assert "checked_total" in generator and "CanBindSparse" in generator
assert "python3 -B tools/check-vulkan-multirange-overflow-host.py" in workflow
cpp = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <span>
using u32 = std::uint32_t;
using VkDeviceSize = std::uint64_t;
using VkDeviceMemory = std::uint64_t;
constexpr VkDeviceMemory VK_NULL_HANDLE = 0;
struct MultiRangeSource {
    VkDeviceMemory memory;
    u32 memory_type;
    VkDeviceSize memory_offset, offset, size;
};
struct MultiRangeBufferCache {
    bool use_sparse = true;
    VkDeviceSize block_size = 65536;
    u32 sparse_memory_type_bits = 1;
    bool CanBindSparse(std::span<const MultiRangeSource>) const;
};
INJECT_CAN
bool Preflight(std::span<const MultiRangeSource> sources, VkDeviceSize total) {
INJECT_PRE
    return true;
}
int main() {
    constexpr VkDeviceSize B=65536;
    constexpr auto MAX=std::numeric_limits<VkDeviceSize>::max();
    MultiRangeBufferCache c;
    std::array<MultiRangeSource,2> valid{{{1,0,0,0,B},{1,0,B,0,B}}};
    assert(c.CanBindSparse(valid) && Preflight(valid,2*B));
    assert(Preflight(valid,3*B));
    assert(!Preflight(valid,B));
    auto bad=valid;
    bad[0].memory_offset=MAX-1023; bad[0].offset=2048;
    assert(!c.CanBindSparse(bad) && !Preflight(bad,2*B));
    bad=valid; bad[0].memory_offset=MAX-(B-1);
    assert(!c.CanBindSparse(bad) && !Preflight(bad,2*B));
    bad=valid; bad[0].size=0;
    assert(!c.CanBindSparse(bad) && !Preflight(bad,2*B));
    bad=valid; bad[0].memory_type=32; assert(!c.CanBindSparse(bad));
    bad=valid; bad[0].memory=0; assert(!c.CanBindSparse(bad));
    c.use_sparse=false; assert(!c.CanBindSparse(valid)); c.use_sparse=true;
    c.block_size=0; assert(!c.CanBindSparse(valid)); c.block_size=B;
    assert(!c.CanBindSparse(std::span<const MultiRangeSource>{}));
    assert(!Preflight(std::span<const MultiRangeSource>{},0));
    std::puts("ENCORE_MULTIRANGE_SPARSE_BOUNDS_PASS");
}
""".replace("INJECT_CAN",can).replace(
    "INJECT_PRE",pre.replace("return SparseBuffer{};","return false;"))
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-sparse-bounds-") as folder:
    src = Path(folder) / "sparse.cpp"
    exe = Path(folder) / "sparse"
    src.write_text(cpp)
    subprocess.run([compiler, "-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(src),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("HOST_MULTIRANGE_BOUNDS_PASS; native device and FPS unmeasured")


# Geometry identity must include actual Vulkan memory backing, not merely the
# buffer handle/offset/size. Rebinding one handle must invalidate sparse reuse.
hash_start = "u64 MultiRangeBufferCache::HashSources(std::span<const MultiRangeSource> sources) const {"
hash_end = "\nu64 MultiRangeBufferCache::HashContent("
assert source.count(hash_start) == 1
hash_body = source[source.index(hash_start):source.index(hash_end, source.index(hash_start))]
for field in ("source.handle", "source.memory", "source.memory_offset",
              "source.memory_type", "source.offset", "source.size"):
    assert f"mix(u64({field}));" in hash_body
assert "source.memory_offset" in generator and "HashSources" in generator
hash_program = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <span>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using VkDeviceSize = u64;
using VkBuffer = u64;
using VkDeviceMemory = u64;
struct MultiRangeSource {
    VkBuffer handle{};
    VkDeviceMemory memory{};
    VkDeviceSize memory_offset{};
    VkDeviceSize offset{};
    VkDeviceSize size{};
    u64 write_tick{};
    u32 memory_type{};
};
class MultiRangeBufferCache {
public:
    u64 HashSources(std::span<const MultiRangeSource>) const;
};
INJECT_HASH
int main() {
    MultiRangeBufferCache cache;
    MultiRangeSource a{17, 23, 0, 0, 65536, 4, 1};
    const u64 baseline = cache.HashSources({&a, 1});
    a.write_tick = 19;
    assert(cache.HashSources({&a, 1}) == baseline);
    a.memory = 29; assert(cache.HashSources({&a, 1}) != baseline); a.memory=23;
    a.memory_offset=65536; assert(cache.HashSources({&a, 1}) != baseline); a.memory_offset=0;
    a.memory_type=2; assert(cache.HashSources({&a, 1}) != baseline); a.memory_type=1;
    a.offset=65536; assert(cache.HashSources({&a, 1}) != baseline); a.offset=0;
    a.size=131072; assert(cache.HashSources({&a, 1}) != baseline); a.size=65536;
    a.handle=18; assert(cache.HashSources({&a, 1}) != baseline); a.handle=17;
    assert(cache.HashSources({&a, 1}) == baseline);
    std::puts("ENCORE_MULTIRANGE_BACKING_IDENTITY_PASS");
}
""".replace("INJECT_HASH", hash_body)
with tempfile.TemporaryDirectory(prefix="encore-multirange-geometry-") as folder:
    src = Path(folder) / "geometry.cpp"
    exe = Path(folder) / "geometry"
    src.write_text(hash_program)
    subprocess.run([compiler, "-std=c++20","-O2","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(src),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("HOST_MULTIRANGE_BACKING_IDENTITY_PASS; console not tested")
