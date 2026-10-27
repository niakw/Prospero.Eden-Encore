#!/usr/bin/env python3
"""Compile the selected Vulkan PipelineCache destructor with queued shader writes.

The PS5 shutdown path must drain accepted serializer jobs before saving the
driver pipeline cache; the desktop path retains its original behavior.
Check the generator reproduces the same order, no live-draw wait introduced.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
shader=(root/"vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
worker=(root/"vendor/sources/eden/src/common/thread_worker.h").read_text()
start="PipelineCache::~PipelineCache() {"
end="\n\nnamespace {\nstd::mutex eden_attributeless_mutex;"
assert shader.count(start)==1 and shader.count(end)==1
method=start+shader.split(start,1)[1].split(end,1)[0]
assert method.count("serialization_thread.WaitForRequests();")==1
assert method.index("serialization_thread.WaitForRequests();") < method.index("SerializeVulkanPipelineCache(")
assert "#ifdef PS5_NATIVE" in method and "#endif" in method
assert "f07_drain_old" in gen and "f07_drain_new" in gen
assert gen.index("shader_source = shader_source.replace(f07_drain_old, f07_drain_new, 1)") < gen.index("shader_output.write_text(shader_source)")
assert "thread.request_stop();" in worker
assert "work_done >= work_scheduled" in worker
assert "requests.emplace(std::move(work));" in worker

# P0.1: a metadata serialization queue failure must not prevent the
# graphics/compute pipeline already compiled by Create*Pipeline from returning.
# Keep both native wrappers reproducible by the pinned source generator.
for kind, start, finish in (
    ("Graphics", "std::unique_ptr<GraphicsPipeline> PipelineCache::CreateGraphicsPipeline() {",
     "std::unique_ptr<ComputePipeline> PipelineCache::CreateComputePipeline("),
    ("Compute", "std::unique_ptr<ComputePipeline> PipelineCache::CreateComputePipeline(\\n    const ComputePipelineCacheKey",
     "std::unique_ptr<ComputePipeline> PipelineCache::CreateComputePipeline(\\n    ShaderPools&"),
):
    start = start.replace("\\\\n", "\\n")
    finish = finish.replace("\\\\n", "\\n")
    assert shader.count(start) == 1 and finish in shader, (kind, "source anchors")
    body = shader.split(start, 1)[1].split(finish, 1)[0]
    assert body.count("serialization_thread.QueueWork(") == 1, kind
    assert body.count("catch (const std::exception& error)") == 1, kind
    assert body.count("catch (...)") == 1, kind
    assert body.index("try {") < body.index("serialization_thread.QueueWork(") < body.index(
        "catch (const std::exception& error)") < body.index("QueueVulkanPipelineCacheFlush()"), kind
    assert "return pipeline;" in body, kind
    assert "shader cache write not queued" in body, kind
    assert ("f07_serializer_" + kind.lower() + "_old") in gen, kind
    assert ("f07_serializer_" + kind.lower() + "_new") in gen, kind


cpp=r"""
#include <cassert>
#include <cstddef>
#include <functional>
#include <string>
#include <utility>
#include <vector>
constexpr unsigned CACHE_VERSION=18;
void EdenResetStaticVertexInputBinding() noexcept {}
struct Worker {
    std::vector<std::function<void()>> jobs;
    bool drained{};
    void QueueWork(std::function<void()> job) { jobs.push_back(std::move(job)); }
    void WaitForRequests() {
        for (auto& job:jobs) job();
        jobs.clear();
        drained=true;
    }
};
class PipelineCache {
public:
    Worker serialization_thread;
    bool use_vulkan_pipeline_cache{true};
    std::string vulkan_pipeline_cache_filename{"driver.bin"};
    bool metadata_persisted{};
    bool driver_saved_after_metadata{};
    void SerializeVulkanPipelineCache(const std::string&, int, unsigned) {
#ifdef PS5_NATIVE
        assert(serialization_thread.drained);
#endif
        driver_saved_after_metadata=metadata_persisted;
    }
    int vulkan_pipeline_cache{};
    ~PipelineCache();
};
""" + method + r"""
int main() {
    // Source destructor executes on return; observe effects through captured
    // external counters because its members are destroyed thereafter.
    bool metadata=false;
    {
        PipelineCache cache;
        cache.serialization_thread.QueueWork([&]{metadata=true; cache.metadata_persisted=true;});
    }
#ifdef PS5_NATIVE
    assert(metadata);
#else
    assert(!metadata);
#endif
    bool no_driver=false;
    {
        PipelineCache cache;
        cache.use_vulkan_pipeline_cache=false;
        cache.serialization_thread.QueueWork([&]{no_driver=true;});
    }
#ifdef PS5_NATIVE
    assert(no_driver);
#else
    assert(!no_driver);
#endif
}
"""
compiler=shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler missing"
with tempfile.TemporaryDirectory(prefix="eden-f07-shader-exit-") as temp:
    path=Path(temp)/"exit.cpp"
    path.write_text(cpp)
    for flags in ([], ["-DPS5_NATIVE=1"]):
        for opt in ("-O0","-O2"):
            exe=Path(temp)/("exit"+("ps5" if flags else "desktop")+opt[1:])
            subprocess.run([compiler,"-std=c++20",opt,*flags,"-Wall","-Wextra",
                            "-Werror",str(path),"-o",str(exe)],check=True,
                           capture_output=True,text=True,timeout=30)
            subprocess.run([str(exe)],check=True,timeout=15)
print("F07_SHADER_CACHE_EXIT_DRAIN_HOST_PASS native=1 desktop=1 O0=1 O2=1")
