#!/usr/bin/env python3
"""F07 P0.1/P0.2: foreground compute shader translation excludes optional optimization.

Extract the actual PS5 native RAII scope from the Vulkan pipeline cache and
compile it at O0/O2. Exercise cold foreground, disk-prewarm exclusion, nested
foreground, exception unwind and early return. No PS5 performance claim.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
compute = (root / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()
graphics = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()

scope_start = "struct ComputeTranslationPriorityScope {"
scope_end = "\n};\n#endif\nusing Shader::Backend::SPIRV::EmitSPIRV;"
assert source.count(scope_start) == source.count(scope_end) == 1
scope = source[source.index(scope_start):source.index(scope_end) + len("\n};")]
assert scope.count("pending_first_use_compute_builds.fetch_add(1, std::memory_order_release)") == 1
assert scope.count("pending_first_use_compute_builds.fetch_sub(1, std::memory_order_release)") == 1
method_start = "    PipelineStatistics* statistics, bool build_in_parallel) try {"
method_end = "    auto hash = key.Hash();\n    if (device.HasBrokenCompute()) {"
assert source.count(method_start) == 1
fragment = source[source.index(method_start) + len(method_start):source.index(method_end, source.index(method_start))]
assert "ComputeTranslationPriorityScope translation_priority{build_in_parallel};" in fragment
assert "pending_first_use_compute_builds{0};" in compute
assert "pending_first_use_compute_builds.load(std::memory_order_acquire)" in graphics
assert "F07 foreground compute shader translation scope" in generator
assert "F07 compute CFG IR SPIRV fairness before driver queue" in generator
assert "std::atomic<unsigned> pending_first_use_compute_builds{0};" not in source
assert source.index("ComputeTranslationPriorityScope translation_priority") < source.index(
    "Shader::Maxwell::Flow::CFG cfg{env, pools.flow_block, env.StartAddress()};"
)

cpp = r"""
#include <atomic>
#include <cassert>
#include <stdexcept>
namespace Vulkan {
std::atomic<unsigned> pending_first_use_compute_builds{0};
namespace {
""" + scope + r"""
}
void Check(bool foreground, bool fail) {
    ComputeTranslationPriorityScope translation_priority{foreground};
    assert(pending_first_use_compute_builds.load(std::memory_order_acquire) ==
           (foreground ? 1u : 0u));
    if (fail) throw std::runtime_error("shader translation failed");
}
void CheckNested() {
    ComputeTranslationPriorityScope translation_priority{true};
    assert(pending_first_use_compute_builds.load(std::memory_order_acquire) == 1);
    Check(false, false);
    assert(pending_first_use_compute_builds.load(std::memory_order_acquire) == 1);
    Check(true, false);
    assert(pending_first_use_compute_builds.load(std::memory_order_acquire) == 1);
    ComputeTranslationPriorityScope extra{true};
    assert(pending_first_use_compute_builds.load(std::memory_order_acquire) == 2);
}
}
int main() {
    using namespace Vulkan;
    for (int i = 0; i < 200; ++i) {
        Check(false, false);
        assert(pending_first_use_compute_builds.load() == 0);
        Check(true, false);
        assert(pending_first_use_compute_builds.load() == 0);
        try { Check(true, true); }
        catch (const std::runtime_error&) {}
        assert(pending_first_use_compute_builds.load() == 0);
        CheckNested();
        assert(pending_first_use_compute_builds.load() == 0);
    }
}
"""
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-compute-translation-") as d:
    source_file = Path(d) / "translation.cpp"
    source_file.write_text(cpp)
    for opt in ("-O0", "-O2"):
        exe = Path(d) / ("translation" + opt[1:])
        built = subprocess.run(
            [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
             "-fsanitize=undefined", "-fno-sanitize-recover=all",
             str(source_file), "-o", str(exe)],
            capture_output=True, text=True, timeout=45)
        assert built.returncode == 0, (opt, built.stderr[-5000:])
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, (opt, result.stdout, result.stderr[-5000:])
print("F07_COMPUTE_TRANSLATION_PRIORITY_PASS runtime=1 disk_preload=0"
      " exception_unwind=1 nested=1 O0=1 O2=1")
