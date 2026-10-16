#!/usr/bin/env python3
"""Source-extracted Clear scissor clipping, including INT32_MIN, under sanitizers."""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
old = "const u32 shrink = (std::min)(extent, static_cast<u32>(-offset));"
new = "const u32 shrink = (std::min)(extent, static_cast<u32>(-static_cast<s64>(offset)));"
assert pinned.count(old) == 1
assert native.count(old) == 0 and native.count(new) == 1
start = native.index("const auto clamp_rect_to_render_area = [render_area](VkRect2D& rect) -> bool {")
opened = native.index("{", start)
depth = 0
end = None
for index in range(opened, len(native)):
    if native[index] == "{":
        depth += 1
    elif native[index] == "}":
        depth -= 1
        if depth == 0:
            end = index + 2
            break
assert end is not None
actual = native[start:end]
assert actual.endswith("};")
assert actual.count(new) == 1
assert actual.count("clamp_axis(") == 2
assert "if (!clamp_rect_to_render_area(clear_rect.rect))" in native

tree = ast.parse(generator)
pairs = []
for node in ast.walk(tree):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "adapt" and len(node.args) >= 3
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "src/video_core/renderer_vulkan/vk_rasterizer.cpp"):
        for item in node.args[2].elts:
            try:
                pair = ast.literal_eval(item)
            except (ValueError, SyntaxError, TypeError):
                continue
            if isinstance(pair, tuple) and len(pair) == 2:
                pairs.append(pair)
assert pairs.count((old,new)) == 1
assert "python3 -B tools/check-ps5-clear-scissor-overflow-host.py" in workflow

cpp = r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <limits>
using s32 = std::int32_t;
using s64 = std::int64_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
struct VkOffset2D { s32 x, y; };
struct VkExtent2D { u32 width, height; };
struct VkRect2D { VkOffset2D offset; VkExtent2D extent; };
struct VkRenderArea { u32 width, height; };
static u32 ReferenceExtent(s32 offset, u32 extent, u32 limit) {
    const s64 left = offset;
    const s64 right = left + static_cast<s64>(extent);
    const s64 first = (std::max)(s64{0}, left);
    const s64 last = (std::min)(static_cast<s64>(limit), right);
    return last > first ? static_cast<u32>(last-first) : 0;
}
int main() {
    constexpr std::array<s32,10> offsets{
        std::numeric_limits<s32>::min(), std::numeric_limits<s32>::min()+1,
        -16384,-1920,-2,-1,0,1,16384,std::numeric_limits<s32>::max()};
    constexpr std::array<u32,8> extents{
        0,1,2,3,4,1920,16384,std::numeric_limits<u32>::max()};
    constexpr std::array<u32,6> limits{0,1,2,1080,1920,16384};
    std::uint64_t checks=0;
    for (const u32 x_limit : limits) {
        for (const u32 y_limit : limits) {
            const VkRenderArea render_area{x_limit, y_limit};
__SOURCE__
            for (const s32 x : offsets) for (const s32 y : offsets) {
                for (const u32 width : extents) for (const u32 height : extents) {
                    VkRect2D rect{{x,y},{width,height}};
                    const auto expected_x=ReferenceExtent(x,width,x_limit);
                    const auto expected_y=ReferenceExtent(y,height,y_limit);
                    const bool valid=clamp_rect_to_render_area(rect);
                    assert(rect.extent.width==expected_x);
                    assert(rect.extent.height==expected_y);
                    assert(valid==(expected_x!=0 && expected_y!=0));
                    if (expected_x) assert(rect.offset.x>=0);
                    if (expected_y) assert(rect.offset.y>=0);
                    ++checks;
                }
            }
        }
    }
    assert(checks==230400);
}
""".replace("__SOURCE__", actual)
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang required"
with tempfile.TemporaryDirectory(prefix="encore-clear-scissor-") as temp:
    src = Path(temp)/"witness.cpp"
    binary = Path(temp)/"witness"
    src.write_text(cpp)
    subprocess.run([clang,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(src),"-o",str(binary)],check=True,timeout=45)
    subprocess.run([str(binary)],check=True,timeout=30)
print("CLEAR_SCISSOR_OVERFLOW_HOST_PASS INT32_MIN=1 sanitizer=1 cases=230400 generator_parity=1")
