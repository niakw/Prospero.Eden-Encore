#!/usr/bin/env python3
"""Native indirect-draw null sentinel: compile real cache binding/getter bodies."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cache = (root / "vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
raster = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
legacy = (root / "vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h").read_text()

def method(source, signature, end="\ntemplate <class P>"):
    at = source.index(signature)
    assert source.count(signature) == 1
    tail = source.find(end, at+len(signature))
    if tail < 0:
        # GetDrawIndirectBuffer is the final method before the namespace close.
        tail = source.index("\n} // namespace VideoCommon", at)
    return source[at:tail].rstrip()

names = [
    "void BufferCache<P>::BindHostDrawIndirectBuffers() {",
    "std::pair<typename BufferCache<P>::Buffer*, u32> BufferCache<P>::GetDrawIndirectCount() {",
    "std::pair<typename BufferCache<P>::Buffer*, u32> BufferCache<P>::GetDrawIndirectBuffer() {"
]
sections = [method(cache, name) for name in names]
assert all("NULL_BUFFER_ID || binding.size == 0" in sec for sec in sections)
assert all("NULL_BUFFER_ID || binding.size == 0" not in method(legacy, name)
           for sec, name in zip(sections, names))
draw = method(raster, "void RasterizerVulkan::DrawIndirect() {", "\nvoid RasterizerVulkan::DrawTexture()")
assert draw.index("if (!buffer)") < draw.index("buffer->Handle()")
assert draw.index("if (!draw_buffer)") < draw.index("draw_buffer->Handle()")
assert draw.count("if (!buffer)") == draw.count("if (!draw_buffer)") == 1
assert "buffer_cache.SetDrawIndirect(nullptr);" in draw
# Both native OpenGL profiles also use this shared BufferCache getter.
for profile in ("gl_rasterizer.cpp", "gl_rasterizer_dev.cpp"):
    gl = (root / "vendor/encore-active/eden-core/src/video_core/renderer_opengl" / profile).read_text()
    gl_draw = method(gl, "void RasterizerOpenGL::DrawIndirect() {", "\nvoid RasterizerOpenGL::DrawTexture()")
    assert gl_draw.index("if (!buffer)") < gl_draw.index("buffer->Handle()"), profile
    assert gl_draw.index("if (!draw_buffer)") < gl_draw.index("draw_buffer->Handle()"), profile

# Disabled post-store experiment must not reintroduce a null Vulkan submit.
deferred = (root / "vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp").read_text()
guest_draw = method(deferred, "void RasterizerVulkan::DrawIndirect() {", "\nvoid RasterizerVulkan::DrawTexture()")
# The native command worker checks the pipeline bound by ConfigureDraw;
# the disabled guest-bridge keeps its original CanExecuteDraw accessor.
# Only that intentional three-call accessor difference is permitted.
assert draw.count("CanExecuteRecordedDraw()") == 3
assert guest_draw.count("CanExecuteDraw()") == 3
assert guest_draw.replace("CanExecuteDraw()", "CanExecuteRecordedDraw()") == draw


code = r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <utility>
using u32 = std::uint32_t;
using DAddr = std::uint64_t;
using BufferId = u32;
constexpr BufferId NULL_BUFFER_ID = 0;
struct Binding { DAddr device_addr{}; u32 size{}; BufferId buffer_id{}; };
struct State { Binding count_buffer_binding{}; Binding indirect_buffer_binding{}; };
struct Indirect { bool include_count{}; };
template <class P> struct BufferCache {
    struct Buffer {
        u32 Offset(DAddr addr) { return static_cast<u32>(addr-100); }
    };
    std::array<Buffer,3> slot_buffers{};
    State* channel_state{};
    Indirect* current_draw_indirect{};
    unsigned touches{}, syncs{};
    void TouchBuffer(Buffer&, BufferId id) { assert(id); ++touches; }
    void SynchronizeBuffer(Buffer&, DAddr, u32 bytes) {
        assert(bytes); ++syncs;
    }
    void BindHostDrawIndirectBuffers();
    std::pair<Buffer*,u32> GetDrawIndirectCount();
    std::pair<Buffer*,u32> GetDrawIndirectBuffer();
};
""" + "\n\n".join("template <class P>\n"+s for s in sections) + r"""
int main() {
    State state{};
    Indirect params{};
    BufferCache<void> cache{};
    cache.channel_state = &state;
    cache.current_draw_indirect = &params;
    // Null sentinel must never be synchronized or used as a command buffer.
    auto empty = cache.GetDrawIndirectBuffer();
    assert(empty.first == nullptr && empty.second == 0);
    assert(cache.GetDrawIndirectCount().first == nullptr);
    params.include_count = true;
    cache.BindHostDrawIndirectBuffers();
    assert(cache.syncs == 0 && cache.touches == 0);
    // A real mapped indirect command is still synchronized and offset.
    state.indirect_buffer_binding = {112,64,1};
    assert(cache.GetDrawIndirectBuffer().first == &cache.slot_buffers[1]);
    assert(cache.GetDrawIndirectBuffer().second == 12);
    cache.BindHostDrawIndirectBuffers();
    assert(cache.syncs == 1 && cache.touches == 1);
    // Missing count buffer must not borrow the normal indirect buffer.
    assert(cache.GetDrawIndirectCount().first == nullptr);
    state.count_buffer_binding = {124,4,2};
    assert(cache.GetDrawIndirectCount().first == &cache.slot_buffers[2]);
    cache.BindHostDrawIndirectBuffers();
    assert(cache.syncs == 3 && cache.touches == 3);
    state.indirect_buffer_binding.size = 0;
    assert(cache.GetDrawIndirectBuffer().first == nullptr);
    cache.BindHostDrawIndirectBuffers();
    assert(cache.syncs == 4 && cache.touches == 4);
    // A non-count draw touches only the live indirect binding.
    state.indirect_buffer_binding = {112,64,1};
    params.include_count = false;
    cache.BindHostDrawIndirectBuffers();
    assert(cache.syncs == 5 && cache.touches == 5);
}
"""
compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++ compiler required"
with tempfile.TemporaryDirectory(prefix="encore-indirect-null-") as tmp:
    source = Path(tmp) / "indirect.cpp"
    source.write_text(code)
    for opt in ("-O0", "-O2"):
        binary = Path(tmp) / ("indirect" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined",
                        "-fno-sanitize-recover=all", str(source), "-o",
                        str(binary)], check=True, timeout=45)
        subprocess.run([str(binary)], check=True, timeout=20)
        print("NATIVE_INDIRECT_NULL_BINDING_PASS", opt)
