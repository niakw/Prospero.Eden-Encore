#!/usr/bin/env python3
"""F07: keep cold shader and texture CPU stall attribution on the shipping PS5 path.

Checks the exact tracked native sources AND the pinned-source generator.
The graphics first-use timer must count all cold shader compilations only with
Detailed Logging enabled. The texture stages must remain nested in the
existing 1-in-16 sampled refresh; quiet paths must never take a clock reading.
No drawings, barriers, mutexes or async worker semantics may change.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
gen = (root / "tools/prepare-vulkan-port.py").read_text()
pipeline = (root / "vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
tex = (root / "vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
perf = (root / "headless/performance.h").read_text()
report = (root / "headless/performance.cpp").read_text()

names = (
    ("GraphicsPipelineCreate", "graphics_pipeline_create"),
    ("ShaderPoolReset", "shader_pool_reset"),
    ("ShaderCfg", "shader_cfg"),
    ("ShaderIr", "shader_ir"),
    ("ShaderSpirv", "shader_spirv"),
    ("ShaderModule", "shader_module"),
    ("TextureUploadStaging", "texture_upload_staging"),
    ("TextureUploadContents", "texture_upload_contents"),
    ("TextureUploadBarrier", "texture_upload_barrier"),
)
for enum_name, log_name in names:
    assert perf.count(enum_name) == 1, enum_name
    assert report.count('"' + log_name + '"') == 1, log_name
    assert enum_name in gen, enum_name

# Exact active shader phase sites and generation policy.
for stage, expected in (("ShaderPoolReset",2), ("ShaderCfg",3),
                        ("ShaderIr",3), ("ShaderSpirv",2), ("ShaderModule",2)):
    assert pipeline.count("CachePhase::"+stage) == expected, stage
    assert stage in gen, stage
assert pipeline.count("cfg_stage_cost.Stop();") == 3
assert "if len(re.findall(cfg_match, shader_source)) != 3:" in gen
assert 'if shader_source.count(f07_pipeline_old) != 1:' in gen
assert "shader_source = shader_source.replace(f07_pipeline_old, f07_pipeline_new, 1)" in gen
assert "texture_costs.append((" in gen
assert "return (++sequence & 15u) == 0u;" in perf
assert "explicit CachePhaseTimer(CachePhase phase, bool enabled = cache_draw_sample_active)" in perf

start = pipeline.index("    if (is_new) {\n#ifdef PS5_NATIVE\n        // F07:")
end = pipeline.index("\n    if (!pipeline)", start)
block = pipeline[start:end]
assert block.count("pipeline = CreateGraphicsPipeline();") == 1
assert block.index("CachePhase::GraphicsPipelineCreate") < block.index(
    "pipeline = CreateGraphicsPipeline();")
assert "detailed_gpu_profile.load(std::memory_order_relaxed)" in block
assert "#ifdef PS5_NATIVE" in block and "#endif" in block
assert "current_pipeline->AddTransition(pipeline.get());" in pipeline

refresh_start = tex.index("void TextureCache<P>::RefreshContents(")
refresh_end = tex.index("\ntemplate <class P>", refresh_start)
refresh = tex[refresh_start:refresh_end]
assert refresh.count("TextureCpuRefresh") == 1
assert refresh.index("if (False(image.flags & ImageFlagBits::CpuModified))") < refresh.index(
    "TextureCpuRefresh")
assert refresh.count("runtime.InsertUploadMemoryBarrier();") == 1
prev = refresh.index("    auto staging = runtime.UploadStagingBuffer(MapSizeBytes(image));")
assert refresh.index("TextureUploadStaging") < prev
for phase, call in (
    ("TextureUploadContents", "UploadImageContents(image, staging);"),
    ("TextureUploadBarrier", "runtime.InsertUploadMemoryBarrier();"),
):
    assert prev < refresh.index(phase) < refresh.index(call), phase
    prev = refresh.index(call)
for token in ("staging_phase.Stop();", "contents_phase.Stop();", "barrier_phase.Stop();"):
    assert refresh.count(token) == 1
assert refresh.count("UploadImageContents(image, staging);") == 1
assert "image.flags &= ~ImageFlagBits::CpuModified;" in refresh
assert "    ::Eden::Performance::CachePhaseTimer upload_phase{" in refresh

# Compile the exact newly generated cold-path block on both PS5/native and
# non-PS5 hosts. Simulate hot/cold misses and diagnostics off/on. The
# real CachePhaseTimer implementation is independently C++-compiled by R310.
cpp = r"""
#include <atomic>
#include <cassert>
namespace Eden::Performance {
enum class CachePhase { GraphicsPipelineCreate };
inline std::atomic<bool> detailed_gpu_profile{false};
inline int profiled = 0;
struct CachePhaseTimer {
    CachePhaseTimer(CachePhase, bool enabled) { if (enabled) ++profiled; }
};
}
int creates = 0;
int CreateGraphicsPipeline() { return ++creates; }
void Check(bool is_new) {
    int pipeline = 0;
""" + block + r"""
    (void)pipeline;
}
int main() {
    Check(false);
    assert(creates == 0 && Eden::Performance::profiled == 0);
    Check(true);
    assert(creates == 1 && Eden::Performance::profiled == 0);
    Eden::Performance::detailed_gpu_profile.store(true);
    Check(false);
    assert(creates == 1 && Eden::Performance::profiled == 0);
    Check(true);
#ifdef PS5_NATIVE
    assert(Eden::Performance::profiled == 1);
#else
    assert(Eden::Performance::profiled == 0);
#endif
    assert(creates == 2);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++")
assert compiler, "Host C++ compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-cold-stalls-") as d:
    source = Path(d) / "probe.cpp"
    binary = Path(d) / "probe"
    source.write_text(cpp)
    for defines in ([], ["-DPS5_NATIVE=1"]):
        subprocess.run(
            [compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
             *defines, str(source), "-o", str(binary)], check=True, timeout=45
        )
        subprocess.run([str(binary)], check=True, timeout=15)
print("PASS F07 pinned generator + native pipeline event timing + texture stage attribution")
