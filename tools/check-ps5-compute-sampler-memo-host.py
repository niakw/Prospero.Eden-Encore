#!/usr/bin/env python3
"""Exercise PS5 compute sampler memo extracted from the selected Vulkan source.

The bounded sampler lookup memo is LOCAL TO ONE Configure call. This compiles
the actual code fragment, checks collision handling and descriptor epochs,
and verifies generator/source parity. No console throughput claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()
generator = (ROOT / "tools/prepare-vulkan-port.py").read_text()
texture = (ROOT / "vendor/encore-active/eden-backports/src/video_core/texture_cache/texture_cache.h").read_text()
raster = (ROOT / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
assert '#include <array>' in source
assert "F01 16-slot compute sampler memo limited to each Configure call" in generator
begin_mark = "#ifdef PS5_NATIVE\n    // Descriptor synchronization above fixes the TSC table for this dispatch."
begin = source.index(begin_mark)
end = source.index("\n#endif", begin) + len("\n#endif")
memo = source[begin:end]
assert memo in generator, "selected native sampler memo diverged from strict generator"
assert "std::array<ComputeSamplerMemo, 16> sampler_memo{};" in memo
assert "entry.valid &&" not in memo
assert "entry.handle != handle" in memo
assert "texture_cache.GetSamplerId(handle, true)" in memo
start = source.index("bool ComputePipeline::Configure(")
stop = source.index("\n} // namespace Vulkan", start)
configure = source[start:stop]
assert configure.index("texture_cache.SynchronizeDescriptors(true);") < configure.index(begin_mark)
assert "samplers.push_back(resolve_sampler(handle.second));" in configure
assert "#else\n            VideoCommon::SamplerId sampler = texture_cache.GetSamplerId(handle.second, true);" in configure
assert raster.index("pipeline->PreflightDescriptorScratch();") < raster.index(
    "std::scoped_lock lock{texture_cache.mutex, buffer_cache.mutex};",
    raster.index("void RasterizerVulkan::DispatchCompute()"))
# The actual sampler resolver consults current compute sampler table, not an
# index shared between graphics and compute stages. Memo only reuses equal IDs
# after this method's TSC synchronization under paired GPU-cache locks.
assert "compute ? channel_state->compute_sampler_table" in texture
assert "channel_state->compute_sampler_table.Synchronize" in texture

code = r"""
#include <array>
#include <cassert>
#include <cstdint>
#include <vector>
using u32 = std::uint32_t;
namespace VideoCommon {
struct SamplerId {
    std::uint32_t value{};
    bool operator==(const SamplerId&) const = default;
};
}
struct FakeTextureCache {
    std::uint32_t epoch{};
    int calls{};
    VideoCommon::SamplerId GetSamplerId(u32 handle, bool compute) {
        assert(compute);
        ++calls;
        return {epoch * 1000 + handle};
    }
};
static std::vector<VideoCommon::SamplerId> Run(FakeTextureCache& texture_cache,
                                                const std::vector<u32>& handles) {
""" + memo + r"""
    std::vector<VideoCommon::SamplerId> output;
    for (u32 handle : handles) {
        output.push_back(resolve_sampler(handle));
    }
    return output;
}
int main() {
    FakeTextureCache cache{};
    const std::vector<u32> handles{2,2,18,18,2,1,1,17,1,17};
    const auto first = Run(cache, handles);
    assert(first.size() == handles.size());
    assert(cache.calls == 7);  // modulo-16 collisions still resolve correctly
    for (size_t i = 0; i < first.size(); ++i)
        assert(first[i].value == handles[i]);
    cache.epoch = 42; // new dispatch: the same IDs must be re-read, not stale
    const auto next = Run(cache, handles);
    assert(cache.calls == 14);
    for (size_t i = 0; i < next.size(); ++i)
        assert(next[i].value == 42000 + handles[i]);
    // Same hash bucket with distinct sampler handles cannot alias IDs.
    // A braced initializer contains commas: never place it inside assert().
    const std::vector<u32> colliding_handles{0,16,32,48,0};
    const auto colliding = Run(cache, colliding_handles);
    assert(cache.calls == 19);
    for (size_t i = 0; i < colliding.size(); ++i)
        assert(colliding[i].value == 42000 + colliding_handles[i]);
    // A descriptor-free compute dispatch does not look up a sampler.
    const int before = cache.calls;
    assert(Run(cache, {}).empty());
    assert(cache.calls == before);
}
"""
compilers = list(dict.fromkeys(filter(None, (
    shutil.which("clang++"), shutil.which("g++"), shutil.which("c++")))))
assert compilers, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-compute-sampler-") as d:
    cpp = Path(d) / "sampler.cpp"
    cpp.write_text(code)
    for compiler in compilers:
        for opt in ("-O0", "-O2"):
            exe = Path(d) / (Path(compiler).name + opt)
            build = subprocess.run(
                [compiler, "-std=c++20", opt, "-DPS5_NATIVE", "-Wall", "-Wextra",
                 "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 str(cpp), "-o", str(exe)],
                capture_output=True, text=True, timeout=50)
            assert build.returncode == 0, (compiler, opt, build.stderr[-5000:])
            ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            assert ran.returncode == 0, (compiler, opt, ran.stderr[-5000:])
            print("ENCORE_PS5_COMPUTE_SAMPLER_MEMO_PASS", Path(compiler).name, opt)
