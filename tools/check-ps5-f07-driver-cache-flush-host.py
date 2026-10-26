#!/usr/bin/env python3
"""F07: compile the exact active async pipeline cache flush scheduling method.

Verify normal save, serialization failure, driver read failure and worker
enqueue failure can never strand flush_in_flight, while unchanged rate-limits
are preserved. The release always uses the same native worker and cache.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
begin="void PipelineCache::QueueVulkanPipelineCacheFlush() {"
end="\n\nGraphicsPipeline* PipelineCache::CurrentGraphicsPipelineSlowPath() {"
assert source.count(begin)==1 and source.count(end)==1
method=begin+source.split(begin,1)[1].split(end,1)[0]
assert method.count("flush_in_flight.store(false, std::memory_order_release)") == 2
assert "struct ReleaseFlush" in method and "catch (const std::exception& error)" in method
assert "f07_flush_old" in generator and "f07_flush_new" in generator
assert "shader_source.count(f07_flush_old) != 1" in generator

code=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <functional>
#include <stdexcept>
#include <string>
#include <utility>
#define Render_Vulkan 1
template<class... Ts> void fake_log(Ts&&...) {}
#define LOG_WARNING(...) fake_log(__VA_ARGS__)
constexpr unsigned CACHE_VERSION=18;
constexpr size_t VULKAN_CACHE_FLUSH_PIPELINES=128;
constexpr size_t VULKAN_CACHE_FLUSH_MIN_SECONDS=30;
struct TestCache {
    bool throw_read{};
    void Read(size_t* n, void*) { if(throw_read) throw std::runtime_error("read"); *n=128; }
};
struct SerializationThread {
    bool throw_enqueue{};
    template<class F> void QueueWork(F fn) { if(throw_enqueue) throw std::runtime_error("enqueue"); fn(); }
};
struct PipelineCache {
    bool use_vulkan_pipeline_cache{true};
    std::string vulkan_pipeline_cache_filename{"pipeline.bin"};
    std::atomic_bool flush_in_flight{false};
    size_t pipelines_since_flush{127};
    std::chrono::steady_clock::time_point last_flush{};
    std::atomic_size_t last_cache_size{0};
    SerializationThread serialization_thread;
    TestCache vulkan_pipeline_cache;
    bool throw_serialize{};
    void SerializeVulkanPipelineCache(const std::string&, TestCache&, unsigned) {
        if(throw_serialize) throw std::runtime_error("save");
    }
    void QueueVulkanPipelineCacheFlush();
};
""" + method + r"""
int main() {
    PipelineCache normal;
    normal.QueueVulkanPipelineCacheFlush();
    assert(!normal.flush_in_flight.load());
    assert(normal.last_cache_size.load()==128);
    assert(normal.pipelines_since_flush==0);
    // Time gate must remain intact even after threshold reached.
    normal.pipelines_since_flush=127;
    normal.QueueVulkanPipelineCacheFlush();
    assert(normal.pipelines_since_flush==128);
    PipelineCache io;
    io.vulkan_pipeline_cache.throw_read=true;
    io.QueueVulkanPipelineCacheFlush();
    assert(!io.flush_in_flight.load());
    io.vulkan_pipeline_cache.throw_read=false;
    io.pipelines_since_flush=127;
    io.last_flush={};
    io.QueueVulkanPipelineCacheFlush();
    assert(io.last_cache_size==128);
    PipelineCache save;
    save.throw_serialize=true;
    save.QueueVulkanPipelineCacheFlush();
    assert(!save.flush_in_flight.load());
    PipelineCache queue;
    queue.serialization_thread.throw_enqueue=true;
    queue.QueueVulkanPipelineCacheFlush();
    assert(!queue.flush_in_flight.load());
}
"""
compiler=shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++ compiler unavailable"
with tempfile.TemporaryDirectory(prefix="eden-f07-flush-") as directory:
    file=Path(directory)/"flush.cpp"
    file.write_text(code)
    for mode in ("-O0","-O2"):
        exe=Path(directory)/("flush"+mode[1:])
        subprocess.run([compiler,"-std=c++20","-pthread",mode,"-Wall","-Wextra","-Werror",
                        str(file),"-o",str(exe)],check=True,capture_output=True,text=True,timeout=40)
        subprocess.run([str(exe)],check=True,timeout=15)
print("F07_DRIVER_CACHE_FLUSH_HOST_PASS normal=1 failed_save=1 failed_read=1 failed_enqueue=1 budget=1")
