#!/usr/bin/env python3
"""F07 native compute cache failure recovery, real source extraction and O0/O2."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
gen = (root / "tools/prepare-vulkan-port.py").read_text()
pinned = (root / "vendor/sources/eden/src/video_core/renderer_vulkan/vk_pipeline_cache.h").read_text()
begin = "    const auto [pair, is_new]{compute_cache.try_emplace(key)};"
stop = "    if (::Eden::DevVulkan::trace_pipelines && pipeline) {"
assert src.count(begin) == 1 and src.count(stop) == 1
body = src[src.index(begin):src.index(stop, src.index(begin))]
assert body.count("CreateComputePipeline(key, shader)") == 2
assert "failed_compute_retries.size() < 32" in body
assert "std::chrono::seconds(2)" in body
assert body.index("failed->second.attempted = true;") < body.rindex("pipeline = CreateComputePipeline(key, shader);")
assert "F07 bounded failed compute shader retry state" in gen
assert "F07 one delayed compute shader retry" in gen
assert "failed_compute_retries" not in pinned

cpp = r"""
#include <cassert>
#include <chrono>
#include <map>
#include <memory>
class PipelineCache {
public:
    struct ComputeRetryState {
        std::chrono::steady_clock::time_point eligible_at{};
        bool attempted{};
    };
    std::map<int, std::unique_ptr<int>> compute_cache;
    std::map<int, ComputeRetryState> failed_compute_retries;
    int key{}, create_calls{};
    bool recover_on_second{};
    std::unique_ptr<int> CreateComputePipeline(int, const int*) {
        ++create_calls;
        if (recover_on_second && create_calls == 2)
            return std::make_unique<int>(42);
        return nullptr;
    }
    void Probe() {
        const int* shader = &key;
""" + body + r"""
    }
};
int main() {
    PipelineCache recovered;
    recovered.recover_on_second = true;
    recovered.Probe();
    assert(recovered.create_calls == 1 && recovered.failed_compute_retries.size() == 1);
    for (int i = 0; i < 1024; ++i) recovered.Probe();
    assert(recovered.create_calls == 1);
    recovered.failed_compute_retries[0].eligible_at =
        std::chrono::steady_clock::now() - std::chrono::seconds(1);
    recovered.Probe();
    assert(recovered.create_calls == 2 && *recovered.compute_cache.at(0) == 42);
    assert(recovered.failed_compute_retries.empty());
    for (int i = 0; i < 1024; ++i) recovered.Probe();
    assert(recovered.create_calls == 2);

    PipelineCache persistent;
    persistent.Probe();
    persistent.failed_compute_retries[0].eligible_at =
        std::chrono::steady_clock::now() - std::chrono::seconds(1);
    persistent.Probe();
    assert(persistent.create_calls == 2 && !persistent.compute_cache.at(0));
    for (int i = 0; i < 1024; ++i) persistent.Probe();
    assert(persistent.create_calls == 2);

    PipelineCache full;
    for (int i = 0; i < 32; ++i)
        full.failed_compute_retries.emplace(i, PipelineCache::ComputeRetryState{});
    full.key = 33;
    full.Probe();
    assert(full.create_calls == 1 && full.failed_compute_retries.size() == 32);
    for (int i = 0; i < 1024; ++i) full.Probe();
    assert(full.create_calls == 1);
}
"""
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-compute-retry-") as folder:
    path = Path(folder) / "compute.cpp"
    path.write_text(cpp)
    for mode in ("-O0", "-O2"):
        exe = Path(folder) / ("compute" + mode[1:])
        subprocess.run([compiler, "-std=c++20", mode, "-DPS5_NATIVE=1",
                        "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                        "-fno-sanitize-recover=all", str(path), "-o", str(exe)],
                       check=True, timeout=40)
        subprocess.run([str(exe)], check=True, timeout=20)
print("F07_FAILED_COMPUTE_RETRY_PASS bounded=32 cooldown=2s retry=1 O0=1 O2=1")
