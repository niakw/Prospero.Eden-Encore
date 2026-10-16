#!/usr/bin/env python3
"""Guard native Vulkan vertex binding count from unsigned reversed-range wrap."""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "vendor/encore-active/eden-vulkan/vk_buffer_cache_cost.cpp").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_buffer_cache.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
anchor = "void BufferCacheRuntime::BindVertexBuffers("
method = native.split(anchor, 1)[1].split(
    "\nvoid BufferCacheRuntime::BindTransformFeedbackBuffer(", 1)[0]
old = """    const u32 min_binding = (std::min)(bindings.min_index, device_max);
    const u32 max_binding = (std::min)(bindings.max_index, device_max);
    const u32 binding_count = max_binding - min_binding;
    if (binding_count == 0) {
        return;
    }"""
new = """    const u32 min_binding = (std::min)(bindings.min_index, device_max);
    const u32 max_binding = (std::min)(bindings.max_index, device_max);
    // Do not wrap a reversed binding range into a huge Vulkan binding count.
    if (max_binding <= min_binding) {
        return;
    }
    const u32 binding_count = max_binding - min_binding;"""
assert old in pinned
assert method.count(new) == 1
assert method.index(new) < method.index("if (device.IsExtExtendedDynamicStateSupported())")
assert "python3 -B tools/check-ps5-vertex-binding-range-host.py" in workflow

tree = ast.parse(generator)
pairs = []
for node in ast.walk(tree):
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "vk_buffer_cache":
                for item in value.elts:
                    try:
                        pair = ast.literal_eval(item)
                    except (ValueError, TypeError, SyntaxError):
                        continue
                    if isinstance(pair, tuple) and len(pair) == 2:
                        pairs.append(pair)
assert pairs.count((old, new)) == 1

# Extract the actual native range clamp and early-return logic into a
# host-compiled witness. No source reimplementation of the guard.
prefix = method[method.index("    const u32 device_max ="):method.index(
    "    if (device.IsExtExtendedDynamicStateSupported())")]
assert prefix.count("return;") == 1
cpp = r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <limits>
using u32 = std::uint32_t;
struct Device {
    u32 max;
    u32 GetMaxVertexInputBindings() const {return max;}
};
struct Bindings {u32 min_index, max_index;};
struct Witness {
    Device device;
    Bindings bindings;
    u32 count=0;
    void Bind() {
__PREFIX__
        count = binding_count;
    }
};
int main() {
    auto check=[](u32 min, u32 max, u32 cap, u32 count){
        Witness w{{cap},{min,max}};
        w.Bind();
        assert(w.count==count);
    };
    check(0,4,16,4);
    check(3,5,16,2);
    check(3,30,16,13);
    check(16,30,16,0);
    check(7,7,16,0);
    check(8,4,16,0);
    check(19,10,16,0);
    check(0,2,0,0);
    check(std::numeric_limits<u32>::max(),0,16,0);
    check(0,std::numeric_limits<u32>::max(),16,16);
}
""".replace("__PREFIX__", prefix)
clang=shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang with ASan/UBSan required"
with tempfile.TemporaryDirectory(prefix="encore-vertex-bind-") as tmp:
    src=Path(tmp)/"witness.cpp";bin=Path(tmp)/"witness"
    src.write_text(cpp)
    subprocess.run([clang,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(src),"-o",str(bin)],check=True,timeout=45)
    subprocess.run([str(bin)],check=True,timeout=30)
print("VERTEX_BINDING_RANGE_HOST_PASS normal=3 clamped=2 reversed=3 empty=2")
