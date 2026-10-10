#!/usr/bin/env python3
"""Compile the production Vulkan texture-GC pressure arithmetic under host sanitizers.

Tests the exact header used in the PS5 generated texture cache. This does not
emulate GPU residency/driver allocation, and is not a native PS5 build.
"""
import ast
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
# Extract the pinned GC rewrite instead of trusting a standalone math model.
# The generated GC has THREE call sites: prefetch and two cleanup passes.
assert 'unsafe_cutoff = "frame_tick - ticks_to_destroy"' in generator
assert 'if gc.count(unsafe_cutoff) != 3:' in generator
assert 'gc = gc.replace(unsafe_cutoff,' in generator
assert '"::Eden::VulkanMemory::OldestEvictionTick(frame_tick, ticks_to_destroy)"' in generator
assert "constexpr std::uint64_t OldestEvictionTick(" in header
assert "return frame_tick >= min_age ? frame_tick - min_age : 0;" in header
assert '#include "vulkan_gc_budget.h"' in generator
assert generator.count("(gc_original, gc)") == 1
# Extract real Python replacement templates; literal backslash-n would emit
# malformed C++ and would not be caught by arithmetic-only C++ tests.
tree = ast.parse(generator)
replacements = {}
for node in ast.walk(tree):
    if (isinstance(node, ast.Tuple) and len(node.elts) == 2
            and isinstance(node.elts[0], ast.Constant)
            and isinstance(node.elts[0].value, str)
            and node.elts[0].value.startswith("total_used_memory -= ")):
        replacements[node.elts[0].value] = ast.literal_eval(node.elts[1])
expected = ("total_used_memory -= GetScaledImageSizeBytes(image);",
            "total_used_memory -= Common::AlignUp(tentative_size, 1024);")
assert set(replacements) == set(expected), replacements.keys()
for old in expected:
    generated = replacements[old]
    assert "if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>)" in generated
    assert "AfterProjectedEviction(" in generated
    assert old in generated  # OpenGL path remains unchanged
    assert "\\n" not in generated  # actual multiline generated C++ required
    assert generated.count("{") == 2 and generated.count("}") == 2
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
using Eden::VulkanMemory::OldestEvictionTick;
static_assert(OldestEvictionTick(0, 10) == 0);
static_assert(OldestEvictionTick(9, 10) == 0);
static_assert(OldestEvictionTick(10, 10) == 0);
static_assert(OldestEvictionTick(11, 10) == 1);
static_assert(OldestEvictionTick(24, 25) == 0);
static_assert(OldestEvictionTick(49, 50) == 0);
static_assert(OldestEvictionTick(50, 50) == 0);
static_assert(OldestEvictionTick(51, 50) == 1);
static_assert(OldestEvictionTick(UINT64_MAX, UINT64_MAX) == 0);
static_assert(OldestEvictionTick(UINT64_MAX, 10) == UINT64_MAX - 10);
int main() {
    // Reproduce the actual startup path: frame_tick begins at zero, while
    // immediate VRAM pressure can enter the texture collector before frame 50.
    // For a new image touched on this frame, the cutoff must NEVER select it
    // as older than any age; the old wrap made cutoff enormous.
    for (std::uint64_t frame = 0; frame < 110; ++frame)
    for (std::uint64_t age : {10ULL, 25ULL, 50ULL}) {
        const auto cutoff = OldestEvictionTick(frame, age);
        const auto expected = frame >= age ? frame - age : 0;
        assert(cutoff == expected);
        assert(cutoff <= frame);
        if (frame < age)
            assert(cutoff == 0);
        if (frame > age)
            assert(cutoff < frame);
    }

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
        const auto frame = next(state), age = next(state);
        const auto cutoff = OldestEvictionTick(frame, age);
        assert(cutoff == (frame >= age ? frame - age : 0));
        assert(cutoff <= frame);
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
print("PASS actual Vulkan GC budget + both LRU cutoffs: 200000 saturation cases and early-frame eviction gates ASan/UBSan")
print("GPU driver, real VRAM headroom, FC27 textures/FPS: not console qualified")
