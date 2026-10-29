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
    ("GraphicsShaderEnvironment", "graphics_shader_environment"),
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
assert pipeline.count("CachePhase::GraphicsShaderEnvironment") == 1
# This interval must surround only the graphics GPU-owner preparation, not a
# worker or a widened guest buffer/texture lock.
environment_start = pipeline.index("CachePhase::GraphicsShaderEnvironment")
assert "GetGraphicsEnvironments(environments, graphics_key.unique_hashes);" in pipeline[
    environment_start:environment_start+400]
assert "detailed_gpu_profile.load(std::memory_order_relaxed)" in pipeline[
    environment_start:environment_start+210]
assert "shader_source.count(f07_environment_old) != 1" in gen
assert "shader_source.replace(f07_environment_old, f07_environment_new, 1)" in gen
assert pipeline.count("cfg_stage_cost.Stop();") == 3
assert "if len(re.findall(cfg_match, shader_source)) != 3:" in gen
assert 'if shader_source.count(f07_pipeline_old) != 1:' in gen
assert "shader_source = shader_source.replace(f07_pipeline_old, f07_pipeline_new, 1)" in gen
assert "texture_costs.append((" in gen
assert "return (++sequence & 15u) == 0u;" in perf
assert "explicit CachePhaseTimer(CachePhase phase, bool enabled = cache_draw_sample_active)" in perf

# Native cold-miss keyed trace is exactly the maintained C++ helper
# replayed by the strict Vulkan generator. It must not run on hot draws.
trace_start = pipeline.index("struct ColdShaderMissTrace {")
trace_end = pipeline.index("\n};\n#endif", trace_start) + len("\n};")
cold_trace = pipeline[trace_start:trace_end]
assert cold_trace in gen
assert pipeline.count("ColdShaderMissTrace cold_miss{") == 2
assert pipeline.count("ColdShaderMissTrace cold_retry{") == 2
assert gen.count("F07 record exact graphics cold first-use CPU cost") == 1
assert gen.count("F07 record exact compute cold first-use CPU cost") == 1
assert "if (!enabled) return;" in cold_trace
assert "steady_clock::now() - started" in cold_trace
assert 'EDEN_VULKAN_SHADER_MISS kind=%s key=%016llx retry=%u ' in cold_trace
assert "success=%u cpu_ns=%llu\\n" in cold_trace
start = pipeline.index("    if (is_new) {\n#ifdef PS5_NATIVE\n        // F07:")
# The slow path now has a separate, bounded failed-key recovery branch.
# This older harness tests ONLY the original cold-miss timer contract;
# the full retry block is source-extracted in its dedicated host test.
first_create = "        pipeline = CreateGraphicsPipeline();"
end = pipeline.index("        cold_miss.Complete(static_cast<bool>(pipeline));", start) + len("        cold_miss.Complete(static_cast<bool>(pipeline));")
block = pipeline[start:end] + "\n#endif\n    }"
assert block.count("pipeline = CreateGraphicsPipeline();") == 1
assert block.index("CachePhase::GraphicsPipelineCreate") < block.index(
    "pipeline = CreateGraphicsPipeline();")
assert "detailed_gpu_profile.load(std::memory_order_relaxed)" in block
assert "#ifdef PS5_NATIVE" in block and "#endif" in block
assert "current_pipeline->AddTransition(pipeline.get());" in pipeline
assert "first_use_cpu_phase.Stop();\n        cold_miss.Complete" in pipeline
assert "first_use_compute_cost.Stop();\n        cold_miss.Complete" in pipeline
assert "retry_cpu_cost.Stop();\n            cold_retry.Complete" in pipeline
assert "retry_compute_cost.Stop();\n            cold_retry.Complete" in pipeline

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
#include <chrono>
#include <cstdint>
#include <cstdio>
using u64 = std::uint64_t;
namespace Eden::Performance {
enum class CachePhase { GraphicsPipelineCreate };
inline std::atomic<bool> detailed_gpu_profile{false};
inline int profiled = 0;
struct CachePhaseTimer {
    CachePhaseTimer(CachePhase, bool enabled) { if (enabled) ++profiled; }
    void Stop() noexcept {}
};
}
#ifdef PS5_NATIVE
""" + cold_trace + r"""
#endif
struct GraphicsPipelineCacheKey { u64 Hash() const noexcept { return 0x1234; } };
GraphicsPipelineCacheKey graphics_key;
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
        executed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
        assert executed.returncode == 0, (defines, executed.stderr[-3000:])
        # Only the second, detailed/native cold miss prints; hot and quiet
        # miss paths remain silent, and desktop is entirely unchanged.
        assert executed.stdout.count("EDEN_VULKAN_SHADER_MISS") == (
            1 if defines else 0), (defines, executed.stdout)

# P0.1: compile the EXACT source-derived graphics shader failure handler.
# In quiet PS5 mode it must not reconstruct CFGs or write .ash files.
# Developer opt-in still dumps; secondary diagnostic exceptions are contained.
catch_anchor = "} catch (const Shader::Exception& exception) {"
function_anchor = "std::unique_ptr<GraphicsPipeline> PipelineCache::CreateGraphicsPipeline(\n    ShaderPools& pools"
start = pipeline.index(catch_anchor, pipeline.index(function_anchor))
end = pipeline.index("\n}\n\nstd::unique_ptr<GraphicsPipeline> PipelineCache::CreateGraphicsPipeline()", start) + 2
catch_fragment = pipeline[start:end]
assert catch_fragment.count("env.Dump(hash, key.unique_hashes[index]);") == 1
assert "if (Settings::values.dump_guest_shaders)" in catch_fragment
assert "Failed shader diagnostic dump:" in catch_fragment
assert "F07 PS5 skip duplicate CFG and dumps after shader exception unless opted in" in gen

shader_exception_fixture = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <span>
#include <stdexcept>
#include <utility>
using u32 = std::uint32_t;
using u64 = std::uint64_t;
unsigned errors{}, warnings{}, built_cfgs{}, dumps{}, hashes{};
bool fail_cfg{}, fail_dump{};
namespace Settings {
struct Values { bool dump_guest_shaders{}; };
inline Values values{};
}
namespace Maxwell { inline constexpr std::size_t MaxShaderProgram = 6; }
namespace Shader {
struct Exception : std::runtime_error { using std::runtime_error::runtime_error; };
struct ProgramHeader { u64 bytes[2]; };
struct Environment {
    u64 StartAddress() const { return 32; }
    void Dump(u64, u64) {
        ++dumps;
        if (fail_dump) throw std::runtime_error("mock disk failure");
    }
};
namespace Maxwell::Flow {
struct CFG {
    CFG(Shader::Environment&, int&, u32, bool) {
        ++built_cfgs;
        if (fail_cfg) throw std::runtime_error("mock CFG failure");
    }
};
}
}
namespace Eden::Performance {
enum class CachePhase { ShaderCfg };
inline std::atomic_bool detailed_gpu_profile{false};
struct CachePhaseTimer {
    CachePhaseTimer(CachePhase, bool){}
    void Stop() {}
};
struct Timer {};
inline std::optional<Timer> VulkanTimer(unsigned) {
    return std::optional<Timer>{std::in_place};
}
}
#define LOG_ERROR(...) do { ++errors; } while(false)
#define LOG_WARNING(...) do { ++warnings; } while(false)
struct GraphicsPipeline {};
struct ShaderPools { int flow_block{}; };
struct Key {
    std::array<u64, 6> unique_hashes{11, 22, 0, 0, 0, 0};
    u64 Hash() const { ++hashes; return 33; }
};
std::unique_ptr<GraphicsPipeline> Probe(
    ShaderPools& pools, const Key& key,
    std::span<Shader::Environment* const> envs) try {
    throw Shader::Exception("original shader exception");
""" + catch_fragment + r"""
int main() {
    ShaderPools pools{};
    Key key{};
    Shader::Environment first{}, second{};
    std::array<Shader::Environment*, 2> stages{&first, &second};
    const auto reset = [] {
        errors = warnings = built_cfgs = dumps = hashes = 0;
        fail_cfg = fail_dump = false;
    };
    reset();
    Settings::values.dump_guest_shaders = false;
    assert(!Probe(pools, key, stages));
#ifdef PS5_NATIVE
    assert(errors == 1 && warnings == 0);
    assert(built_cfgs == 0 && dumps == 0 && hashes == 0);
#else
    assert(errors == 1 && built_cfgs == 2 && dumps == 2 && hashes == 1);
#endif
    reset();
    Settings::values.dump_guest_shaders = true;
    assert(!Probe(pools, key, stages));
    assert(errors == 1 && warnings == 0 && built_cfgs == 2 && dumps == 2);
#ifdef PS5_NATIVE
    reset();
    fail_cfg = true;
    assert(!Probe(pools, key, stages));
    assert(errors == 1 && warnings == 1 && built_cfgs == 1 && dumps == 0);
    reset();
    fail_dump = true;
    assert(!Probe(pools, key, stages));
    assert(errors == 1 && warnings == 1 && built_cfgs == 1 && dumps == 1);
#endif
}
"""
with tempfile.TemporaryDirectory(prefix="eden-f07-shader-failure-dump-") as directory:
    source_file = Path(directory) / "shader_failure.cpp"
    source_file.write_text(shader_exception_fixture)
    for defines in ([], ["-DPS5_NATIVE=1"]):
        for opt in ("-O0", "-O2"):
            binary = Path(directory) / ("failure" + opt[1:] +
                                        ("-native" if defines else "-desktop"))
            command = [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                       *defines, str(source_file), "-o", str(binary)]
            built = subprocess.run(command, capture_output=True, text=True, timeout=40)
            assert built.returncode == 0, (command, built.stderr[-5000:])
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            assert ran.returncode == 0, (defines, opt, ran.stderr[-5000:])
print("F07_SHADER_FAILURE_DUMP_HOST_PASS quiet_no_second_cfg=1 opt_in=1 diagnostic_fail_safe=1 native=1 desktop=1 O0=1 O2=1")

print("PASS F07 pinned generator + native pipeline event timing + texture stage attribution")
