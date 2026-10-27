#!/usr/bin/env python3
"""Validate release/acquire pipeline readiness on both native Vulkan paths.

Extracts the real pre-wait guard from the maintained graphics and compute
translation units. Host C++20 ASan/UBSan exercises already-built and racing
builder paths with shared non-atomic payload. Does NOT prove PS5 FPS.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
FILES=(
    ROOT/"vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp",
    ROOT/"vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp",
)
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
SCRIPT="python3 -B tools/check-vulkan-pipeline-ready-publication-host.py"
assert SCRIPT in FAST and SCRIPT in FULL
GUARD="    if (!is_built.load(std::memory_order_acquire)) {"
for path in FILES:
    text=path.read_text()
    # Graphics uses the acquire guard both in ConfigureDraw and, since F07,
    # in the destructor joining the still-queued first-use builder.
    is_graphics = path.name == "vk_graphics_pipeline_cost.cpp"
    assert text.count(GUARD) == (2 if is_graphics else 1), path
    if is_graphics:
        destroy = text[text.index("GraphicsPipeline::~GraphicsPipeline()"):
                       text.index("void GraphicsPipeline::QueueOptimizedPipeline(")]
        assert destroy.count(GUARD) == 1
        assert destroy.index("build_condvar.wait(build_lock") < destroy.index(
            "const auto state = optimize_state;")
        configure = text[text.index("bool GraphicsPipeline::ConfigureDraw("):
                         text.index("GraphicsPipeline::~GraphicsPipeline()")]
        assert configure.count(GUARD) == 1
    assert text.count("is_built.store(true, std::memory_order_release);")==1,path
    assert "if (!is_built.load(std::memory_order::relaxed)) {" not in text,path
    # A thread that observes ready must acquire the pipeline before BindPipeline.
    assert text.index("is_built.store(true, std::memory_order_release);") < text.index(GUARD)
    assert "build_condvar.wait(lock, [this] { return is_built.load(std::memory_order::relaxed); });" in text

CPP=r"""
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <thread>
struct TestPipeline {
    std::atomic_bool is_built{false};
    std::mutex build_mutex;
    std::condition_variable build_condvar;
    std::uint64_t handle{};
    unsigned took_wait_path{};
    void Build() {
        handle=0x8a55ff0011223344ULL;
        {
            std::scoped_lock lock{build_mutex};
            is_built.store(true, std::memory_order_release);
        }
        build_condvar.notify_all();
    }
    void WaitReady() {
GUARD_INJECT
            ++took_wait_path;
            std::unique_lock lock{build_mutex};
            build_condvar.wait(lock, [this] {
                return is_built.load(std::memory_order_relaxed);
            });
        }
        assert(handle==0x8a55ff0011223344ULL);
    }
};
int main(){
    constexpr unsigned repeats=192;
    unsigned fast{},wait{};
    for(unsigned i=0;i<repeats;++i){
        TestPipeline p;
        p.Build();
        p.WaitReady();
        assert(p.took_wait_path==0);
        ++fast;
    }
    for(unsigned i=0;i<repeats;++i){
        TestPipeline p;
        std::thread worker([&]{p.WaitReady();});
        // Ensure the waiter can actually block and then be notified;
        // immediate publication is also a correct race outcome.
        std::this_thread::yield();
        p.Build();
        worker.join();
        if(p.took_wait_path) ++wait;
    }
    assert(fast==repeats);
    std::printf("VULKAN_PIPELINE_PUBLICATION_PASS ready=%u racing=%u slow=%u\n",
                fast,repeats,wait);
}
""".replace("GUARD_INJECT",GUARD)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-vk-pipeline-ready-") as tmp:
    path=Path(tmp)/"ready.cpp"
    target=Path(tmp)/"ready"
    path.write_text(CPP)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra",
                    "-Werror","-pthread","-fsanitize=address,undefined",
                    "-fno-sanitize-recover=all",str(path),"-o",str(target)],
                   check=True,timeout=90)
    subprocess.run([str(target)],check=True,timeout=30)
print("ENCORE_VULKAN_PIPELINE_PUBLICATION_HOST_PASS sources=2 gpu_console_unmeasured=1")
