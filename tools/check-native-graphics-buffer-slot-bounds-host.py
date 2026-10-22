#!/usr/bin/env python3
"""Compile actual selected graphics binding methods against bounded shader slots."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
current = (root / "vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
base = (root / "vendor/encore-active/eden-backports/src/video_core/buffer_cache/buffer_cache.h").read_text()
base_hdr = (root / "vendor/sources/eden/src/video_core/buffer_cache/buffer_cache_base.h").read_text()
assert "constexpr u32 NUM_STORAGE_BUFFERS = 16;" in base_hdr
assert "constexpr u32 NUM_TEXTURE_BUFFERS = 32;" in base_hdr
assert "constexpr u32 NUM_STAGES = 5;" in base_hdr

def grab(src, signature):
    assert src.count(signature) == 1
    start = src.index(signature)
    return src[start:src.index("\ntemplate <class P>", start + len(signature))].rstrip()

signatures = (
    "bool BufferCache<P>::BindGraphicsStorageBuffer(size_t",
    "void BufferCache<P>::BindGraphicsTextureBuffer(size_t",
    "void BufferCache<P>::BindComputeStorageBuffer(size_t",
)
sections = [grab(current, s) for s in signatures]
for section in sections:
    assert "stage >= NUM_STAGES" in section
    assert "[[unlikely]]" in section
    assert "stage >= NUM_STAGES" not in grab(base, signatures[sections.index(section)])
assert "ssbo_index >= NUM_STORAGE_BUFFERS" in sections[0]
assert "tbo_index >= NUM_TEXTURE_BUFFERS" in sections[1]
assert "cbuf_index >= maxwell3d->state.shader_stages[stage].const_buffers.size()" in sections[0]
assert "cbuf_index >= kepler_compute->launch_description.const_buffer_config.size()" in sections[2]
assert sections[2].index("cbuf_index >= kepler_compute") < sections[2].index(">> cbuf_index")
assert sections[0].index("ssbo_index >= NUM_STORAGE_BUFFERS") < sections[0].index(">> ssbo_index")
assert sections[1].index("tbo_index >= NUM_TEXTURE_BUFFERS") < sections[1].index("<< tbo_index")

program = r"""
#include <array>
#include <bit>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
using u32 = std::uint32_t;
using GPUVAddr = std::uint64_t;
constexpr size_t NUM_STAGES = 5;
constexpr size_t NUM_STORAGE_BUFFERS = 16;
constexpr size_t NUM_TEXTURE_BUFFERS = 32;
enum class PixelFormat { R8 };
#define LOG_ERROR(...) (void)0
#define LOG_WARNING(...) (void)0
struct StorageBinding {
    u32 buffer_id{};
};
struct TextureBinding {
    u32 buffer_id{};
};
struct ConstBuffer { GPUVAddr address{100}; };
struct ShaderStage { std::array<ConstBuffer, 18> const_buffers{}; };
struct StageState { std::array<ShaderStage, NUM_STAGES> shader_stages{}; };
struct Maxwell { StageState state; };
struct ComputeConfig { GPUVAddr Address() const { return 100; } };
struct LaunchDescription {
    u32 const_buffer_enable_mask{0xff};
    std::array<ComputeConfig,8> const_buffer_config{};
};
struct Kepler { LaunchDescription launch_description{}; };
#define ASSERT(cond) assert(cond)
struct State {
    std::array<u32, NUM_STAGES> enabled_storage_buffers{};
    std::array<u32, NUM_STAGES> written_storage_buffers{};
    std::array<u32, NUM_STAGES> enabled_texture_buffers{};
    std::array<u32, NUM_STAGES> written_texture_buffers{};
    std::array<u32, NUM_STAGES> image_texture_buffers{};
    std::array<std::array<StorageBinding, NUM_STORAGE_BUFFERS>, NUM_STAGES> storage_buffers{};
    std::array<std::array<TextureBinding, NUM_TEXTURE_BUFFERS>, NUM_STAGES> texture_buffers{};
    u32 total_graphics_storage_buffers{};
    u32 enabled_compute_storage_buffers{};
    u32 written_compute_storage_buffers{};
    u32 total_compute_storage_buffers{};
    std::array<StorageBinding, NUM_STORAGE_BUFFERS> compute_storage_buffers{};
};
struct Runtime {
    bool limit{};
    bool ShouldLimitDynamicStorageBuffers() const { return limit; }
    u32 GetMaxDynamicStorageBuffers() const { return 16; }
};
constexpr u32 NULL_BUFFER_ID = 0;
template <class P> struct BufferCache {
    static constexpr bool SEPARATE_IMAGE_BUFFERS_BINDINGS = true;
    State* channel_state{};
    Maxwell* maxwell3d{};
    Kepler* kepler_compute{};
    Runtime runtime{};
    StorageBinding StorageBufferBinding(GPUVAddr, u32, bool) { return {1}; }
    TextureBinding GetTextureBufferBinding(GPUVAddr, u32, PixelFormat) { return {1}; }
    bool BindGraphicsStorageBuffer(size_t stage, size_t ssbo_index, u32 cbuf_index,
                                   u32 cbuf_offset, bool is_written);
    void BindGraphicsTextureBuffer(size_t stage, size_t tbo_index, GPUVAddr gpu_addr,
                                   u32 size, PixelFormat format, bool is_written, bool is_image);
    void BindComputeStorageBuffer(size_t ssbo_index, u32 cbuf_index,
                                  u32 cbuf_offset, bool is_written);
};
""" + "\n\n".join("template <class P>\n"+v for v in sections) + r"""
int main() {
    State state{};
    Maxwell maxwell{};
    Kepler compute{};
    BufferCache<void> cache{};
    cache.kepler_compute = &compute;
    cache.channel_state = &state;
    cache.maxwell3d = &maxwell;
    // Valid endpoints must keep their masks and exact descriptor slots.
    assert(cache.BindGraphicsStorageBuffer(4, 15, 0, 2, true));
    assert(state.enabled_storage_buffers[4] == (u32{1} << 15));
    assert(state.written_storage_buffers[4] == (u32{1} << 15));
    assert(state.storage_buffers[4][15].buffer_id == 1);
    cache.BindGraphicsTextureBuffer(4, 31, 120, 64, PixelFormat::R8, true, true);
    assert(state.enabled_texture_buffers[4] == (u32{1} << 31));
    assert(state.written_texture_buffers[4] == (u32{1} << 31));
    assert(state.texture_buffers[4][31].buffer_id == 1);
    const auto saved_storage = state.enabled_storage_buffers[4];
    const auto saved_texture = state.enabled_texture_buffers[4];
    const auto saved_total = state.total_graphics_storage_buffers;
    // Reject first overflowing index and arbitrary large index.
    for (size_t bad : {size_t{16}, size_t{32}, size_t{1024}}) {
        assert(!cache.BindGraphicsStorageBuffer(4, bad, 0, 2, true));
    }
    for (size_t bad : {size_t{32}, size_t{1024}}) {
        cache.BindGraphicsTextureBuffer(4, bad, 120, 64, PixelFormat::R8, true, true);
    }
    // Reject stage overrun, even for otherwise valid descriptor slots.
    assert(!cache.BindGraphicsStorageBuffer(5, 0, 0, 2, true));
    cache.BindGraphicsTextureBuffer(5, 0, 120, 64, PixelFormat::R8, true, true);
    assert(state.enabled_storage_buffers[4] == saved_storage);
    assert(state.enabled_texture_buffers[4] == saved_texture);
    assert(state.total_graphics_storage_buffers == saved_total);
    // Driver dynamic limit is still accounted only for live bindings.
    cache.runtime.limit = true;
    assert(cache.BindGraphicsStorageBuffer(2, 0, 0, 2, false));
    assert(state.total_graphics_storage_buffers == saved_total + 1);
    assert(!cache.BindGraphicsStorageBuffer(2, 16, 0, 2, false));
    assert(state.total_graphics_storage_buffers == saved_total + 1);
    // Graphics shader constant-buffer array has 18 entries, 0..17 inclusive.
    assert(cache.BindGraphicsStorageBuffer(0, 1, 17, 0, false));
    const auto gfx_before = state.enabled_storage_buffers[0];
    assert(!cache.BindGraphicsStorageBuffer(0, 2, 18, 0, true));
    assert(!cache.BindGraphicsStorageBuffer(0, 2, 1000, 0, true));
    assert(state.enabled_storage_buffers[0] == gfx_before);
    // Compute constant-buffer enable mask and its table only cover 0..7.
    cache.BindComputeStorageBuffer(0, 7, 0, true);
    assert(state.enabled_compute_storage_buffers == 1U);
    assert(state.written_compute_storage_buffers == 1U);
    assert(state.compute_storage_buffers[0].buffer_id == 1);
    auto comp_before = state.total_compute_storage_buffers;
    cache.BindComputeStorageBuffer(1, 8, 0, true);
    cache.BindComputeStorageBuffer(1, 1000, 0, true);
    assert(state.enabled_compute_storage_buffers == 1U);
    assert(state.total_compute_storage_buffers == comp_before);
    // Reject impossible compute CBUF before any shift, array read or dirty mark.
    compute.launch_description.const_buffer_enable_mask = 0;
    cache.BindComputeStorageBuffer(2, 7, 0, true);
    assert(state.compute_storage_buffers[2].buffer_id == 0);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-gfx-bound-") as directory:
    source = Path(directory) / "bound.cpp"
    source.write_text(program)
    for opt in ("-O0", "-O2"):
        binary = Path(directory) / ("bound" + opt)
        subprocess.run([compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                        str(source), "-o", str(binary)], check=True, timeout=45)
        subprocess.run([str(binary)], check=True, timeout=20)
        print("NATIVE_GRAPHICS_SLOT_BOUNDS_PASS", opt)
