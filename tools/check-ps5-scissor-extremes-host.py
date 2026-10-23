#!/usr/bin/env python3
"""Compile the selected Vulkan scissor code and reject the old overflow.

Normal viewport/scissor values must match the pinned source, while hostile
guest register extremes must not overflow before Vulkan clipping. This is a
host correctness witness, not a gameplay/FPS benchmark.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp"
PINNED = ROOT / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp"


def extract(path: Path) -> str:
    text = path.read_text()
    start_marker = "VkRect2D GetScissorState("
    end_marker = "\nDrawParams MakeDrawParams("
    assert text.count(start_marker) == 1 and text.count(end_marker) == 1
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end].strip()


active = extract(ACTIVE)
pinned = extract(PINNED)
assert active != pinned
assert "static_cast<s64>(src.max_x) - src.min_x" in active
assert "static_cast<s64>(clip_height) - src.max_y" in active
assert "down_shift < 32" in active
assert "as_i32 >> down_shift" in active  # Must preserve signed clipping.
assert "bits >> down_shift" not in active
assert "src.max_x - src.min_x" in pinned

mock = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <limits>
using s32 = std::int32_t;
using s64 = std::int64_t;
using u32 = std::uint32_t;
struct VkOffset2D { s32 x{}, y{}; };
struct VkExtent2D { u32 width{}, height{}; };
struct VkRect2D { VkOffset2D offset; VkExtent2D extent; };
struct Field {
    s32 value{};
    operator s32() const { return value; }
    s32 Value() const { return value; }
};
struct Maxwell {
    struct WindowOrigin {
        enum class Mode { UpperLeft, LowerLeft };
        Mode mode{Mode::UpperLeft};
    };
    struct Scissor {
        bool enable{true};
        Field min_x, max_x, min_y, max_y;
    };
    std::array<Scissor, 16> scissor_test{};
    WindowOrigin window_origin{};
    struct { s32 height{}; } surface_clip{};
};
"""

checks = r"""
int main() {
    Maxwell m;
    m.surface_clip.height = 1080;
    // Regression: converting a negative signed coordinate to unsigned BEFORE
    // shifting used to clip the left side to -1 instead of its actual offset.
    m.scissor_test[0] = {true, Field{-96}, Field{8}, Field{10}, Field{60}};
    const auto signed_scissor = GetScissorState(m, 0, 1, 1);
    assert(signed_scissor.offset.x == -48);
    assert(BaselineScissor(m, 0, 1, 1).offset.x == signed_scissor.offset.x);
    for (int x = -96; x < 96; x += 11) {
        for (int y = 0; y < 100; y += 13) {
            for (u32 scale = 1; scale <= 4; ++scale) {
                for (u32 shift = 0; shift <= 2; ++shift) {
                    for (int origin = 0; origin < 2; ++origin) {
                        m.window_origin.mode =
                            origin ? Maxwell::WindowOrigin::Mode::LowerLeft
                                   : Maxwell::WindowOrigin::Mode::UpperLeft;
                        m.scissor_test[0] = {
                            true, Field{x}, Field{x+104}, Field{y}, Field{y+63}
                        };
                        const auto old = BaselineScissor(m, 0, scale, shift);
                        const auto now = GetScissorState(m, 0, scale, shift);
                        assert(old.offset.x == now.offset.x);
                        assert(old.offset.y == now.offset.y);
                        assert(old.extent.width == now.extent.width);
                        assert(old.extent.height == now.extent.height);
                    }
                }
            }
        }
    }

    volatile s32 low = std::numeric_limits<s32>::min();
    volatile s32 high = std::numeric_limits<s32>::max();
    m.scissor_test[0] = {
        true, Field{low}, Field{high}, Field{low}, Field{high}
    };
#ifdef NEGATIVE_OLD_SCISSOR
    // Previous source overflows the signed x-coordinate subtraction here.
    (void)BaselineScissor(m, 0, 2, 0);
    std::puts("OLD_SCISSOR_UNEXPECTEDLY_ACCEPTED_OVERFLOW");
#else
    for (u32 scale : {1U, 2U, 3U, 4U, std::numeric_limits<u32>::max()}) {
        for (u32 shift : {0U, 1U, 31U, 32U, 63U, 64U}) {
            for (int origin = 0; origin < 2; ++origin) {
                m.window_origin.mode =
                    origin ? Maxwell::WindowOrigin::Mode::LowerLeft
                           : Maxwell::WindowOrigin::Mode::UpperLeft;
                const auto result = GetScissorState(m, 0, scale, shift);
                assert(result.extent.width <= std::numeric_limits<s32>::max());
            }
        }
    }
    std::puts("PS5_SCISSOR_SOURCE_EXTRACTED_HOST_PASS");
#endif
}
"""

baseline_method = pinned.replace(
    "VkRect2D GetScissorState(", "VkRect2D BaselineScissor(", 1
)
source = mock + baseline_method + "\n\n" + active + "\n\n" + checks
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler is not None, "C++ compiler unavailable"
with tempfile.TemporaryDirectory(prefix="encore-scissor-") as temp:
    cpp = Path(temp) / "scissor.cpp"
    cpp.write_text(source)
    for opt in ("-O0", "-O2"):
        binary = Path(temp) / ("scissor" + opt)
        flags = [
            compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
            "-fsanitize=undefined", "-fno-sanitize-recover=all",
        ]
        compile_result = subprocess.run(
            [*flags, str(cpp), "-o", str(binary)],
            capture_output=True, text=True, timeout=45
        )
        assert compile_result.returncode == 0, compile_result.stderr[-5000:]
        result = subprocess.run(
            [str(binary)], capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0, (opt, result.stdout, result.stderr)
        assert "PS5_SCISSOR_SOURCE_EXTRACTED_HOST_PASS" in result.stdout

        previous = Path(temp) / ("old" + opt)
        old_build = subprocess.run(
            [*flags, "-DNEGATIVE_OLD_SCISSOR=1", str(cpp), "-o", str(previous)],
            capture_output=True, text=True, timeout=45
        )
        assert old_build.returncode == 0, old_build.stderr[-5000:]
        old = subprocess.run(
            [str(previous)], capture_output=True, text=True, timeout=15
        )
        assert old.returncode != 0 and "signed integer overflow" in old.stderr, (
            "Uncorrected original failed to trigger UBSan", opt,
            old.stdout, old.stderr[-2000:]
        )
        print("PS5_SCISSOR_OVERFLOW_REGRESSION_PASS", opt,
              "normal-parity + extreme-safe + original-UBSan-failure")
