#!/usr/bin/env python3
"""ASan/UBSan: cap Vulkan render-pass clear count at the captured array extent.

Extract the maintained scheduler's actual copy/count preflight into a host
fixture, and assert the subsequent Vulkan command uses the bounded count.
This is a memory-safety property, not a measured PS5 graphics improvement.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp").read_text()
workflow = (ROOT / ".github/workflows/encore-core-preflight.yml").read_text()
start = "    std::array<VkClearValue, 9> values{};"
end = "    Record([renderpass, framebuffer_handle, render_area, values, bounded_clear_value_count]("
assert source.count(start) == 1
assert source.count(end) == 1
body = source[source.index(start):source.index(end)]
assert "const u32 bounded_clear_value_count =" in body
assert "(std::min)(clear_value_count, static_cast<u32>(values.size()))" in body
assert "clear_values ?" in body
assert "i < bounded_clear_value_count" in body
command = source[source.index(end):source.index("cmdbuf.BeginRenderPass(renderpass_bi", source.index(end))]
assert ".clearValueCount = bounded_clear_value_count," in command
assert ".pClearValues = bounded_clear_value_count != 0 ? values.data() : nullptr," in command
assert "python3 -B tools/check-vulkan-renderpass-clear-bounds-host.py" in workflow

test = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>
using u32 = std::uint32_t;
struct VkClearValue { std::uint64_t marker{}; };
static void Probe(const VkClearValue* clear_values, u32 clear_value_count, u32 expected) {
INJECT
    assert(bounded_clear_value_count == expected);
    for (u32 i = 0; i < expected; ++i)
        assert(values[i].marker == clear_values[i].marker);
    for (u32 i = expected; i < values.size(); ++i)
        assert(values[i].marker == 0);
}
int main() {
    std::array<VkClearValue, 9> items{};
    for (u32 i = 0; i < items.size(); ++i)
        items[i].marker = i + 1;
    Probe(nullptr, 0, 0);
    Probe(nullptr, std::numeric_limits<u32>::max(), 0);
    Probe(items.data(), 0, 0);
    Probe(items.data(), 1, 1);
    Probe(items.data(), 9, 9);
    Probe(items.data(), 10, 9);
    Probe(items.data(), std::numeric_limits<u32>::max(), 9);
    std::puts("ENCORE_VULKAN_CLEAR_VALUE_BOUNDS_PASS");
}
""".replace("INJECT", body)
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-vulkan-clear-bounds-") as folder:
    temp = Path(folder)
    src = temp / "clear.cpp"
    binary = temp / "clear"
    src.write_text(test)
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
                    "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", str(src), "-o", str(binary)],
                   check=True, timeout=90)
    subprocess.run([str(binary)], check=True, timeout=30)
print("HOST_CLEAR_COUNT_BOUNDS_PASS; native build/FPS unverified")
