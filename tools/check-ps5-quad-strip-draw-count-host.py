#!/usr/bin/env python3
"""Validate exact native short quad-strip draw math with C++ sanitizers."""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
raster = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
workflow = (root / ".github/workflows/encore-core-preflight.yml").read_text()
upstream = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_rasterizer.cpp").read_text()
cost = (root / "vendor/encore-active/eden-vulkan/vk_buffer_cache_cost.cpp").read_text()
upstream_cost = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_buffer_cache.cpp").read_text()

start = "DrawParams MakeDrawParams("
begin = raster.index(start)
brace = raster.index("{", begin)
depth = 0
stop = None
for i in range(brace, len(raster)):
    if raster[i] == "{":
        depth += 1
    elif raster[i] == "}":
        depth -= 1
        if depth == 0:
            stop = i + 1
            break
assert stop is not None
method = raster[begin:stop]
old = "params.num_vertices = (params.num_vertices - 2) / 2 * 6;"
new = "params.num_vertices = params.num_vertices >= 2 ? (params.num_vertices - 2) / 2 * 6 : 0;"
assert old not in method
assert method.count(new) == 1
assert "params.num_vertices = (params.num_vertices / 4) * 6;" in method
assert old in upstream

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
assert pairs.count((old, new)) == 1
bindname = "void BufferCacheRuntime::BindQuadIndexBuffer("
beginbind = cost.index(bindname)
endbind = cost.index("\nvoid BufferCacheRuntime::BindVertexBuffer(", beginbind)
bind = cost[beginbind:endbind]
assert bind.count("if (count < 4) {") == 1
assert bind.index("if (count < 4) {") < bind.index("ReserveNullBuffer();")
assert bind.index("ReserveNullBuffer();") < bind.index("return;")
assert bind.index("return;") < bind.index("quad_array_index_buffer->UpdateBuffer(")
assert "if (count == 0) {" in upstream_cost[upstream_cost.index(bindname):]
generator_patch = ast.parse(generator)
buffer_pairs=[]
for node in ast.walk(generator_patch):
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "vk_buffer_cache":
                for entry in value.elts:
                    try:
                        pair = ast.literal_eval(entry)
                    except (TypeError, SyntaxError, ValueError):
                        continue
                    if isinstance(pair, tuple) and len(pair) == 2:
                        buffer_pairs.append(pair)
assert len([(a,b) for a,b in buffer_pairs
            if a.startswith(bindname) and "count < 4" in b]) == 1
assert "python3 -B tools/check-ps5-quad-strip-draw-count-host.py" in workflow

cpp = r"""
#include <cassert>
#include <cstdint>
using u32 = std::uint32_t;
namespace Maxwell {
enum class PrimitiveTopology { Quads, QuadStrip, Triangles };
}
namespace Tegra::Engines {
struct Maxwell3D {
    struct DrawManager {
        struct State {
            u32 base_instance{};
            u32 base_index{};
            struct Span { u32 first{}; u32 count{}; };
            Span vertex_buffer{};
            Span index_buffer{};
            Maxwell::PrimitiveTopology topology{Maxwell::PrimitiveTopology::Triangles};
        };
    };
};
}
struct DrawParams {
    u32 base_instance{};
    u32 num_instances{};
    u32 base_vertex{};
    u32 num_vertices{};
    u32 first_index{};
    bool is_indexed{};
};
__FUNCTION__
int main() {
    using State = Tegra::Engines::Maxwell3D::DrawManager::State;
    for (u32 vertices = 0; vertices != 256; ++vertices) {
        State s{};
        s.topology=Maxwell::PrimitiveTopology::QuadStrip;
        s.vertex_buffer={5, vertices};
        s.index_buffer={3, vertices};
        s.base_index=12;
        const u32 expected = vertices < 2 ? 0u : ((vertices - 2u) / 2u) * 6u;
        const DrawParams direct = MakeDrawParams(s, 1, false);
        const DrawParams indexed = MakeDrawParams(s, 2, true);
        assert(direct.num_vertices==expected && indexed.num_vertices==expected);
        assert(direct.is_indexed && indexed.is_indexed);
        assert(direct.base_vertex==0 && indexed.base_vertex==0);
        assert(indexed.first_index==3 && direct.first_index==0);
        s.topology=Maxwell::PrimitiveTopology::Quads;
        const DrawParams quads=MakeDrawParams(s, 1, false);
        assert(quads.num_vertices==(vertices/4u)*6u);
        s.topology=Maxwell::PrimitiveTopology::Triangles;
        const DrawParams triangles=MakeDrawParams(s, 1, false);
        assert(triangles.num_vertices==vertices && !triangles.is_indexed);
    }
}
""".replace("__FUNCTION__", method)
clang = shutil.which("clang++-18") or shutil.which("clang++")
assert clang, "Clang with sanitizers required"
with tempfile.TemporaryDirectory(prefix="encore-quadstrip-") as tmp:
    source=Path(tmp)/"test.cpp"
    binary=Path(tmp)/"test"
    source.write_text(cpp)
    subprocess.run([clang, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                    str(source), "-o", str(binary)], check=True, timeout=45)
    subprocess.run([str(binary)], check=True, timeout=30)
print("QUAD_STRIP_DRAW_COUNT_HOST_PASS short_counts=4 sweep=256 direct=1 indexed=1 quads_unchanged=1 null_quad_lut_guard=1")
