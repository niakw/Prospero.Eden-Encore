#!/usr/bin/env python3
"""F01: compile the real PS5 compute scratch lease and pre-lock preflight.

Validates 0, 1, and 2 nested invocations, a third-invocation fallback, thread
isolation, retained capacity and source-generator parity. Not an FPS claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()
hdr = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_compute_pipeline.h").read_text()
raster = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
cmake = (root / "headless/vulkan.cmake").read_text()
assert '"${PORT_BUILD_DIR}/vk_compute_pipeline_cost.cpp"' in cmake
assert 'set(EDEN_ACTIVE_VULKAN "${PORT_ROOT}/vendor/encore-active/eden-vulkan")' in cmake
assert 'F01 PS5 per-thread reentrant compute descriptor storage' in generator
assert 'F01 compute scratch reservation precedes both guest cache mutexes' in generator
assert "#include <memory>" in src
assert "size_t num_image_elements{};" in hdr and "size_t num_textures{};" in hdr
assert "void PreflightDescriptorScratch();" in hdr

begin = src.index("#ifdef PS5_NATIVE\nnamespace {\n// Per-GPU-thread compute descriptor storage.")
end = src.index("\nComputePipeline::ComputePipeline(", begin)
helper = src[begin:end]
assert helper in generator, "selected compute scratch differs from native generator"
assert helper.count("thread_local ComputeDescriptorScratch") == 2
assert "std::make_unique<ComputeDescriptorScratch>()" in helper
assert "current->views.clear();" in helper and "current->samplers.clear();" in helper

method_start = src.index("void ComputePipeline::PreflightDescriptorScratch() {")
method_end = src.index("\n#endif", method_start)
method = src[method_start:method_end]
assert method in generator, "selected preflight function differs from generator"
assert "num_image_elements" in method and "num_textures" in method
assert "scratch.in_use" in method

configure_start = src.index("bool ComputePipeline::Configure(")
configure_end = src.index("    const auto& qmd{kepler_compute.launch_description};", configure_start)
configure = src[configure_start:configure_end]
assert "ComputeDescriptorScratchLease scratch;" in configure
assert "auto& views = scratch.Views();" in configure
assert "auto& samplers = scratch.Samplers();" in configure
assert "views.reserve(num_image_elements);" in configure
assert "samplers.reserve(num_textures);" in configure
assert "boost::container::small_vector<VideoCommon::ImageViewInOut, 64> views;" in configure
assert configure.index("#ifdef PS5_NATIVE") < configure.index("ComputeDescriptorScratchLease scratch;")
assert configure.index("#else") < configure.index("boost::container::small_vector<VideoCommon::ImageViewInOut, 64> views;")

dispatch_start = raster.index("void RasterizerVulkan::DispatchCompute()")
dispatch_end = raster.index("\nvoid RasterizerVulkan::", dispatch_start + 20)
dispatch = raster[dispatch_start:dispatch_end]
assert dispatch.count("pipeline->PreflightDescriptorScratch();") == 1
assert dispatch.index("pipeline->PreflightDescriptorScratch();") < dispatch.index(
    "std::scoped_lock lock{texture_cache.mutex, buffer_cache.mutex};")
assert dispatch.index("pipeline = pipeline_cache.CurrentComputePipeline();") < dispatch.index(
    "pipeline->PreflightDescriptorScratch();")
assert "void ComputePipeline::PreflightDescriptorScratch()" in src

prologue = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <thread>
#include <boost/container/small_vector.hpp>
namespace VideoCommon {
struct ImageViewInOut { std::uint32_t index{}; };
struct SamplerId { std::uint32_t index{}; };
}
namespace Vulkan {
"""
pipeline = r"""
struct ComputePipeline {
    size_t num_image_elements{};
    size_t num_textures{};
    void PreflightDescriptorScratch();
};
"""
epilogue = r"""
int main() {
    using namespace Vulkan;
    ComputePipeline p{128, 96};
    p.PreflightDescriptorScratch();
    assert(compute_descriptor_scratch.views.capacity() >= 128);
    assert(compute_descriptor_scratch.samplers.capacity() >= 96);
    assert(!compute_descriptor_scratch.in_use);
    {
        ComputeDescriptorScratchLease first;
        assert(compute_descriptor_scratch.in_use);
        first.Views().push_back({.index = 17});
        first.Samplers().push_back({.index = 81});
        p.PreflightDescriptorScratch();
        assert(compute_descriptor_nested_scratch.views.capacity() >= 128);
        assert(compute_descriptor_nested_scratch.samplers.capacity() >= 96);
        {
            ComputeDescriptorScratchLease second;
            second.Views().push_back({.index = 23});
            second.Samplers().push_back({.index = 82});
            assert(second.Views().data() != first.Views().data());
            assert(first.Views().at(0).index == 17);
            // Third depth: retained slots are busy; use one isolated fallback.
            {
                ComputeDescriptorScratchLease third;
                third.Views().push_back({.index = 31});
                assert(third.Views().data() != first.Views().data());
                assert(third.Views().data() != second.Views().data());
            }
            assert(first.Views().at(0).index == 17);
            assert(second.Views().at(0).index == 23);
            p.PreflightDescriptorScratch(); // Both slots busy => harmless no-op.
        }
        // Nested slot released; ready for future reservations.
        assert(!compute_descriptor_nested_scratch.in_use);
        assert(first.Samplers().at(0).index == 81);
    }
    assert(!compute_descriptor_scratch.in_use);
    {
        ComputeDescriptorScratchLease first;
        assert(first.Views().empty() && first.Samplers().empty());
        assert(first.Views().capacity() >= 128);
        assert(first.Samplers().capacity() >= 96);
    }
    std::thread worker([] {
        ComputePipeline p2{100, 70};
        p2.PreflightDescriptorScratch();
        assert(compute_descriptor_scratch.views.capacity() >= 100);
        ComputeDescriptorScratchLease first;
        first.Views().push_back({.index = 1001});
        assert(first.Views().at(0).index == 1001);
    });
    worker.join();
    assert(!compute_descriptor_scratch.in_use);
    ComputePipeline empty{0, 0};
    empty.PreflightDescriptorScratch();
    {
        ComputeDescriptorScratchLease zero;
        assert(zero.Views().empty() && zero.Samplers().empty());
    }
}
"""
code = prologue + helper + "\n" + pipeline + "\n" + method + "\n} // namespace Vulkan\n" + epilogue
compilers = list(dict.fromkeys(filter(None, [
    shutil.which("clang++"), shutil.which("g++"), shutil.which("c++")])))
assert compilers, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f01-compute-scratch-") as tmp:
    cpp = Path(tmp) / "compute.cpp"
    cpp.write_text(code)
    for compiler in compilers:
        for opt in ("-O0", "-O2"):
            exe = Path(tmp) / (Path(compiler).name + opt)
            built = subprocess.run(
                [compiler, "-std=c++20", opt, "-DPS5_NATIVE", "-pthread",
                 "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 str(cpp), "-o", str(exe)],
                text=True, capture_output=True, timeout=55)
            assert built.returncode == 0, (compiler, opt, built.stderr[-5000:])
            ran = subprocess.run([str(exe)], text=True, capture_output=True, timeout=18)
            assert ran.returncode == 0, (compiler, opt, ran.stderr[-5000:])
            print("ENCORE_F01_COMPUTE_SCRATCH_PASS", Path(compiler).name, opt)
