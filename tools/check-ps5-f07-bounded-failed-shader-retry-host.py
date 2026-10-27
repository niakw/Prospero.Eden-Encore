#!/usr/bin/env python3
"""F07: a null first-use graphics cache entry may recover only once.

Source-extracted C++20 policy: no hot-path clock, no unbounded recompiles,
max 64 failed-key records, exact pinned header/generator parity. Host only.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
hdr = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_pipeline_cache.h").read_text()
active = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_pipeline_cache.h").read_text()
cmake = (root / "headless/vulkan.cmake").read_text()
gen = (root / "tools/prepare-vulkan-port.py").read_text()
start = "GraphicsPipeline* PipelineCache::CurrentGraphicsPipelineSlowPath() {"
end = "    if (!pipeline) {\n        return nullptr;"
assert src.count(start) == 1
block = src[src.index(start) + len(start):src.index(end, src.index(start))]
assert block.count("CreateGraphicsPipeline()") == 2
assert "failed_graphics_retries.size() < 64" in block
assert "failed->second.attempted = true;" in block
assert "std::chrono::seconds(2)" in block
assert block.index("failed->second.attempted = true;") < block.rindex("pipeline = CreateGraphicsPipeline();")
assert block.count("CachePhase::GraphicsPipelineCreate") == 2
assert "F07 bounded failed graphics retry state" in gen
assert "F07 one delayed retry for failed graphics shader" in gen
assert "failed_graphics_retries" not in hdr  # the pinned input is immutable
assert active.count("failed_graphics_retries;") == 1
assert active.count("struct GraphicsRetryState") == 1
assert "std::chrono::steady_clock::time_point eligible_at" in active
assert "adapt('src/video_core/renderer_vulkan/vk_pipeline_cache.h'" in gen
assert 'TARGET_DIRECTORY video_core APPEND PROPERTY OBJECT_DEPENDS' in cmake
assert '${PORT_BUILD_DIR}/include/video_core/renderer_vulkan/vk_pipeline_cache.h' in cmake
assert "::Common::unordered_map<GraphicsPipelineCacheKey, std::unique_ptr<GraphicsPipeline>> graphics_cache;" in hdr

cpp = r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <map>
#include <memory>
namespace Eden { namespace Performance {
enum class CachePhase { GraphicsPipelineCreate };
inline std::atomic_bool detailed_gpu_profile{false};
struct CachePhaseTimer { CachePhaseTimer(CachePhase, bool) {} };
}}
class PipelineCache {
public:
    struct GraphicsRetryState {
        std::chrono::steady_clock::time_point eligible_at{};
        bool attempted{};
    };
    std::map<int, std::unique_ptr<int>> graphics_cache;
    std::map<int, GraphicsRetryState> failed_graphics_retries;
    int graphics_key{};
    int create_calls{};
    bool recover_on_second{};
    std::unique_ptr<int> CreateGraphicsPipeline() {
        ++create_calls;
        if (recover_on_second && create_calls == 2)
            return std::make_unique<int>(42);
        return nullptr;
    }
    void Probe() {
""" + block + r"""
    }
};
int main() {
    PipelineCache recovered;
    recovered.recover_on_second = true;
    recovered.Probe();
    assert(recovered.create_calls == 1);
    assert(recovered.failed_graphics_retries.size() == 1);
    for (int i = 0; i < 1024; ++i) recovered.Probe();
    assert(recovered.create_calls == 1);  // cooldown: no per-draw compilation
    recovered.failed_graphics_retries[0].eligible_at =
        std::chrono::steady_clock::now() - std::chrono::seconds(1);
    recovered.Probe();
    assert(recovered.create_calls == 2);
    assert(*recovered.graphics_cache.at(0) == 42);
    assert(recovered.failed_graphics_retries.empty());
    for (int i = 0; i < 1024; ++i) recovered.Probe();
    assert(recovered.create_calls == 2);  // success hot path is unchanged

    PipelineCache persistent;
    persistent.Probe();
    persistent.failed_graphics_retries[0].eligible_at =
        std::chrono::steady_clock::now() - std::chrono::seconds(1);
    persistent.Probe();
    assert(persistent.create_calls == 2);
    assert(!persistent.graphics_cache.at(0));
    for (int i = 0; i < 2048; ++i) persistent.Probe();
    assert(persistent.create_calls == 2);  // one retry, never a storm

    PipelineCache full;
    for (int i = 0; i < 64; ++i)
        full.failed_graphics_retries.emplace(i, PipelineCache::GraphicsRetryState{});
    full.graphics_key = 65;
    full.Probe();
    assert(full.create_calls == 1);
    assert(full.failed_graphics_retries.size() == 64);
    for (int i = 0; i < 1024; ++i) full.Probe();
    assert(full.create_calls == 1);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-failed-shader-") as folder:
    path = Path(folder) / "failed.cpp"
    path.write_text(cpp)
    for mode in ("-O0", "-O2"):
        exe = Path(folder) / ("failed" + mode[1:])
        subprocess.run([compiler, "-std=c++20", mode, "-DPS5_NATIVE=1",
                        "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=undefined", "-fno-sanitize-recover=all",
                        str(path), "-o", str(exe)], check=True, timeout=40)
        subprocess.run([str(exe)], check=True, timeout=20)
print("F07_FAILED_SHADER_RETRY_PASS bounded=64 cooldown=2s once_per_key=1 recovered=1 persistent_failure=1 O0=1 O2=1")
