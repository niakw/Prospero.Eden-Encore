#!/usr/bin/env python3
"""F07: source-extracted release/acquire publication for async Vulkan pipelines.

The scheduler/build worker initializes its non-atomic pipeline handle, then
release-publishes is_built. Both IsBuilt() and CanExecuteDraw() consumers must
acquire before inspecting that handle; no fence, mutex or draw is skipped.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_graphics_pipeline.h").read_text()
active = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
start = "    [[nodiscard]] bool IsBuilt() const noexcept {"
end = "\n\n    template <typename Spec>"
assert header.count(start) == 1, "IsBuilt source must be unique"
methods = start + header.split(start, 1)[1].split(end, 1)[0]
assert methods.count("is_built.load(std::memory_order::acquire)") == 2, "both consumers must acquire"
assert "is_built.load(std::memory_order::relaxed)" not in methods
assert "static_cast<bool>(pipeline)" in methods
assert "is_built.store(true, std::memory_order_release);" in active
assert active.index("is_built.store(true, std::memory_order_release);") < active.index("build_condvar.notify_all();")
assert "ready_source.count(ready_old) != 1" in generator
assert "ready_source.replace(ready_old, ready_new, 1)" in generator

code = r"""
#include <atomic>
#include <cassert>
#include <thread>
#include <memory>
class GraphicsPipeline {
public:
""" + methods + r"""
    std::atomic_bool is_built{false};
    std::shared_ptr<int> pipeline;
};
int main() {
    for (int i = 0; i < 512; ++i) {
        GraphicsPipeline current;
        assert(!current.IsBuilt());
        assert(!current.CanExecuteDraw());
        std::thread build([&] {
            current.pipeline = std::make_shared<int>(81);
            current.is_built.store(true, std::memory_order_release);
        });
        while (!current.IsBuilt()) std::this_thread::yield();
        assert(current.pipeline && *current.pipeline == 81);
        assert(current.CanExecuteDraw());
        build.join();
    }
    // A completed-but-failed shader must still be rejected.
    GraphicsPipeline failed;
    failed.is_built.store(true, std::memory_order_release);
    assert(failed.IsBuilt());
    assert(!failed.CanExecuteDraw());
}
"""
compiler = shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++ compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f07-pipeline-publication-") as folder:
    source = Path(folder) / "source.cpp"
    source.write_text(code)
    for mode in ("-O0", "-O2"):
        exe = Path(folder) / ("ready-" + mode.removeprefix("-"))
        subprocess.run([compiler, "-std=c++20", "-pthread", mode,
                        "-Wall", "-Wextra", "-Werror", str(source), "-o", str(exe)],
                       check=True, capture_output=True, text=True, timeout=40)
        subprocess.run([str(exe)], check=True, timeout=20)
print("F07_PIPELINE_PUBLICATION_PASS release_store=1 acquire_reader=2 failed_build=1 O0=1 O2=1")
