#!/usr/bin/env python3
"""Compile maintained Maxwell draw manager methods: dynamic index spans re-arm dirty."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native_path = "vendor/encore-active/eden-core/src/video_core/engines/draw_manager.cpp"
pinned_path = "vendor/sources/eden/src/video_core/engines/draw_manager.cpp"
native = (root / native_path).read_text()
pinned = (root / pinned_path).read_text()
cmake = (root / "headless/CMakeLists.txt").read_text()
assert 'list(REMOVE_ITEM video_sources engines/draw_manager.cpp)' in cmake
assert 'list(APPEND video_sources "${EDEN_MAINTAINED_DRAW_MANAGER}")' in cmake
assert native_path in cmake

methods = (
    ("DrawIndex", "DrawArrayIndirect"),
    ("DrawIndexedIndirect", "SetInlineIndexBuffer"),
    ("DrawEnd", "DrawIndexSmall"),
)
def extract(text, method, next_method):
    start = "void Maxwell3D::DrawManager::" + method + "("
    end = "void Maxwell3D::DrawManager::" + next_method + "("
    assert text.count(start) == 1
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j].rstrip()

# No other upstream draw manager logic is changed.
expected = pinned
for method, next_method in methods:
    old = extract(pinned, method, next_method)
    new = extract(native, method, next_method)
    assert new.count("changed_index_span") >= 2
    # DrawEnd already has the independent, always-dirty inline-index case.
    expected_dirty_marks = 2 if method == "DrawEnd" else 1
    assert new.count("maxwell3d.dirty.flags[VideoCommon::Dirty::IndexBuffer] = true;") == expected_dirty_marks
    expected = expected.replace(old, new)
assert expected == native, "Unexpected change outside the three reviewed draw entrypoints"

program = r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <vector>
using u32 = std::uint32_t;
namespace VideoCommon { namespace Dirty { constexpr size_t IndexBuffer = 0; } }
struct Maxwell3D {
    struct Regs {
        enum class PrimitiveTopology { Triangles };
        enum class IndexFormat { UnsignedInt };
        struct IndexBuffer { u32 first{}, count{}; IndexFormat format{}; };
        struct VertexBuffer { u32 count{}; };
        IndexBuffer index_buffer{};
        VertexBuffer vertex_buffer{};
        u32 global_base_instance_index{}, global_base_vertex_index{};
    } regs{};
    struct { std::array<bool, 1> flags{false}; } dirty{};
    struct DrawManager {
        enum class DrawMode { General, Instance, InlineIndex };
        struct State {
            Regs::PrimitiveTopology topology{};
            Regs::IndexBuffer index_buffer{};
            Regs::VertexBuffer vertex_buffer{};
            DrawMode draw_mode{DrawMode::General};
            bool draw_indexed{};
            u32 base_index{}, base_instance{};
            std::vector<std::uint8_t> inline_index_draw_indexes{};
        } draw_state{};
        unsigned new_index_bindings{}, executed_draws{}, executed_indirect{};
        void ProcessDraw(Maxwell3D& m, bool indexed, u32) {
            ++executed_draws;
            if (indexed && m.dirty.flags[VideoCommon::Dirty::IndexBuffer]) {
                ++new_index_bindings;
                m.dirty.flags[VideoCommon::Dirty::IndexBuffer] = false;
            }
        }
        void ProcessDrawIndirect(Maxwell3D& m) {
            ++executed_indirect;
            if (m.dirty.flags[VideoCommon::Dirty::IndexBuffer]) {
                ++new_index_bindings;
                m.dirty.flags[VideoCommon::Dirty::IndexBuffer] = false;
            }
        }
        void DrawIndex(Maxwell3D&, Regs::PrimitiveTopology, u32,u32,u32,u32,u32);
        void DrawIndexedIndirect(Maxwell3D&, Regs::PrimitiveTopology, u32,u32);
        void DrawEnd(Maxwell3D&, u32,bool);
    };
};
""" + "\n\n".join(extract(native, method, next_method) for method, next_method in methods) + r"""
int main() {
    Maxwell3D m{};
    Maxwell3D::DrawManager d{};
    using Topology = Maxwell3D::Regs::PrimitiveTopology;
    m.regs.index_buffer.count = 8;
    d.DrawIndex(m, Topology::Triangles, 0, 8, 0, 0, 1);
    assert(d.new_index_bindings == 1);
    d.DrawIndex(m, Topology::Triangles, 0, 8, 0, 0, 1);
    assert(d.new_index_bindings == 1); // same range: no unnecessary cache refresh
    d.DrawIndex(m, Topology::Triangles, 24, 48, 0, 0, 1);
    assert(d.new_index_bindings == 2);
    d.DrawIndexedIndirect(m, Topology::Triangles, 24, 48);
    assert(d.new_index_bindings == 2);
    d.DrawIndexedIndirect(m, Topology::Triangles, 32, 48);
    assert(d.new_index_bindings == 3);
    // Return from a macro draw to the register-owned general draw.
    d.draw_state.draw_mode = Maxwell3D::DrawManager::DrawMode::General;
    d.draw_state.draw_indexed = true;
    d.DrawEnd(m, 1, true);
    assert(d.new_index_bindings == 4);
    d.draw_state.draw_indexed = true;
    d.DrawEnd(m, 1, true);
    assert(d.new_index_bindings == 4);
    // The preexisting dirty register from a regular register write survives.
    m.dirty.flags[VideoCommon::Dirty::IndexBuffer] = true;
    d.DrawIndex(m, Topology::Triangles, 0, 8, 0, 0, 1);
    assert(d.new_index_bindings == 5);
    // Inline indices continue to set their own forced dirty bit.
    d.draw_state.draw_mode = Maxwell3D::DrawManager::DrawMode::InlineIndex;
    d.draw_state.inline_index_draw_indexes = {1, 2, 3, 4};
    d.DrawEnd(m, 1, true);
    assert(d.new_index_bindings == 6);
    assert(d.draw_state.inline_index_draw_indexes.empty());
}
"""
compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-draw-dirty-") as tmp:
    source = Path(tmp) / "draw.cpp"
    source.write_text(program)
    for opt in ("-O0", "-O2"):
        out = Path(tmp) / ("draw" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(source), "-o", str(out)], check=True, timeout=45)
        subprocess.run([str(out)], check=True, timeout=20)
        print("INDEX_DRAW_DIRTY_SPAN_PASS", opt)
