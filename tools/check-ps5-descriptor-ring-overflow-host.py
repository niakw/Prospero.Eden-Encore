#!/usr/bin/env python3
"""Check Vulkan descriptor ring rejects u64 oversize before AlignUp wraps.

Extract the actual native C++ predicate and compile against the pinned real
Common::AlignUp implementation under ASan/UBSan. This test is not evidence of
guest-game stalls or Vulkan GPU execution.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_descriptor_buffer.h").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_descriptor_buffer.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
old = """    [[nodiscard]] bool CanAllocate(VkDeviceSize size) const noexcept {
        return Common::AlignUp(size, alignment) <= chunk_capacity;
    }"""
new = """    [[nodiscard]] bool CanAllocate(VkDeviceSize size) const noexcept {
        // Validate unaligned size before AlignUp can overflow VkDeviceSize.
        return size <= chunk_capacity && Common::AlignUp(size, alignment) <= chunk_capacity;
    }"""
assert pinned.count(old) == 1
assert native.count(new) == 1
assert generator.count("return size <= chunk_capacity && Common::AlignUp(size, alignment) <= chunk_capacity;") == 1
assert 'python3 -B tools/check-ps5-descriptor-ring-overflow-host.py' in workflow
assert "[[nodiscard]] constexpr T AlignUp(T value_, size_t size)" in (root / "vendor/sources/eden/src/common/alignment.h").read_text()

# Compile the verbatim native predicate and original upstream predicate.
# The original admits UINT64_MAX because AlignUp wraps to zero.
cpp = r"""
#include <cassert>
#include <cstdint>
#include <limits>
#include "common/alignment.h"
using VkDeviceSize = std::uint64_t;
struct Ring {
    VkDeviceSize chunk_capacity;
    VkDeviceSize alignment;
__ACTUAL__
__PINNED__
};
int main() {
    constexpr auto max = std::numeric_limits<VkDeviceSize>::max();
    const Ring ring{4092, 16};
    assert(ring.CanAllocate(0));
    assert(ring.CanAllocate(1));
    assert(ring.CanAllocate(16));
    assert(ring.CanAllocate(4080));
    assert(!ring.CanAllocate(4081));
    assert(!ring.CanAllocate(4092));
    assert(!ring.CanAllocate(4096));
    assert(!ring.CanAllocate(max));
    assert(!ring.CanAllocate(max - 7));
    assert(!ring.CanAllocate(max - 15));
    assert(ring.CanAllocatePinned(max));
    const Ring disabled{0, 16};
    assert(!disabled.CanAllocate(max));
    const Ring exact{4096, 16};
    assert(exact.CanAllocate(4096));
    assert(!exact.CanAllocate(4097));
}
""".replace("__ACTUAL__", new).replace("__PINNED__", old.replace("CanAllocate(", "CanAllocatePinned("))
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang C++20 needed"
with tempfile.TemporaryDirectory(prefix="encore-descriptor-overflow-") as tmp:
    source = Path(tmp) / "ring.cpp"
    binary = Path(tmp) / "ring"
    source.write_text(cpp)
    subprocess.run(
        [clang, "-std=c++20", "-O2", "-g", "-Wall", "-Wextra", "-Werror",
         "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
         "-I", str(root / "vendor/sources/eden/src"),
         str(source), "-o", str(binary)],
        check=True, timeout=45)
    subprocess.run([str(binary)], check=True, timeout=30)
print("DESCRIPTOR_RING_OVERFLOW_HOST_PASS normal=7 UINT64_MAX=3 pinned_wrap_reproduced=1")
