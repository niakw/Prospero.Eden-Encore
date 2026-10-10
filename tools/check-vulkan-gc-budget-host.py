#!/usr/bin/env python3
"""Compile the production Vulkan texture-GC pressure arithmetic under host sanitizers.

Tests the exact header used in the PS5 generated texture cache. This does not
emulate GPU residency/driver allocation, and is not a native PS5 build.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "headless/vulkan_gc_budget.h").read_text(encoding="utf-8")
gc = (root / "headless/vulkan_gc_downloads.inc").read_text(encoding="utf-8")
generator = (root / "tools/prepare-vulkan-port.py").read_text(encoding="utf-8")
assert "constexpr std::uint64_t AfterProjectedEviction(" in header
assert "return reclaimed >= used ? 0 : used - reclaimed;" in header
assert "usage = ::Eden::VulkanMemory::AfterProjectedEviction(" in gc
assert "usage -= ReclaimedBytes(image);" not in gc
assert '#include "vulkan_gc_budget.h"' in generator
assert generator.count("(gc_original, gc)") == 1
compiler = next((name for name in ("clang++-18", "clang++", "g++")
                 if shutil.which(name)), None)
if compiler is None:
    raise SystemExit("Missing C++20 compiler; do not mark Vulkan GC host check passed")

source = r"""
#include <cassert>
#include <cstdint>
#include <limits>
#include "vulkan_gc_budget.h"
using Eden::VulkanMemory::AfterProjectedEviction;
static_assert(AfterProjectedEviction(0, 0) == 0);
static_assert(AfterProjectedEviction(0, 1) == 0);
static_assert(AfterProjectedEviction(1, 2) == 0);
static_assert(AfterProjectedEviction(100, 100) == 0);
static_assert(AfterProjectedEviction(100, 99) == 1);
static_assert(AfterProjectedEviction(UINT64_MAX, UINT64_MAX) == 0);
static_assert(AfterProjectedEviction(UINT64_MAX, 1) == UINT64_MAX - 1);
static_assert(AfterProjectedEviction(1, UINT64_MAX) == 0);
int main() {
    std::uint64_t state = 0x534F4E5950533530ULL;
    constexpr auto next = [](std::uint64_t& x) {
        x ^= x << 13; x ^= x >> 7; x ^= x << 17;
        return x;
    };
    for (unsigned i = 0; i < 200000; ++i) {
        auto used = next(state), reclaimed = next(state);
        const auto got = AfterProjectedEviction(used, reclaimed);
        const auto reference = reclaimed >= used ? 0 : used - reclaimed;
        assert(got == reference);
        assert(got <= used);
        assert(AfterProjectedEviction(got, reclaimed) <= got);
    }
}
"""
with tempfile.TemporaryDirectory(prefix="eden-vulkan-gc-budget-") as temp:
    source_path = Path(temp) / "gc.cpp"
    executable = Path(temp) / "gc"
    source_path.write_text(source, encoding="utf-8")
    subprocess.run([compiler, "-std=c++20", "-O1", "-g", "-Wall", "-Wextra",
                    "-Werror", "-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all", "-I", str(root / "headless"),
                    str(source_path), "-o", str(executable)], check=True, timeout=90)
    subprocess.run([str(executable)], check=True, timeout=90)
print("PASS production Vulkan texture GC projected pressure: 200000 bounded cases ASan/UBSan")
print("GPU driver, real VRAM headroom, FC27 textures/FPS: not console qualified")
