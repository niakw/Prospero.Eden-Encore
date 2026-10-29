#!/usr/bin/env python3
"""F07 V01: compile the actual native/desktop FIFO worker-wait callbacks.

Do not infer PS5 game stalls from these simulated build completions.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
perf = (root / "headless/performance.h").read_text()
gen = (root / "tools/prepare-vulkan-port.py").read_text()
cache = (root / "vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_compute_pipeline.h").read_text()
g = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
c = (root / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()

begin = perf.index("struct PipelineWaitTrace {")
end = perf.index("\n};", begin) + len("\n};")
trace = perf[begin:end]
assert "if (!enabled) return;" in trace
assert "wait_ns=%llu usable=%u" in trace
assert "std::chrono::steady_clock::now() - started" in trace
assert "struct ShaderMissStageCosts" in perf
assert "result->SetDiagnosticCacheKeyHash(key.Hash());" in cache
assert "void SetDiagnosticCacheKeyHash(u64 hash) noexcept" in header
assert "u64 diagnostic_cache_key_hash{};" in header
for phrase in (
    "F07 keyed graphics worker-wait diagnostic admission",
    "F07 keyed compute worker-wait diagnostic admission",
    "F07 keyed graphics worker-wait after mutex release",
    "F07 keyed compute worker-wait after mutex release",
    "F07 publish diagnostic compute cache key before first Configure",
):
    assert phrase in gen, phrase

def callback_body(text, kind):
    first = text.index("        scheduler.Record([this](vk::CommandBuffer) {")
    last = text.index("        });", first) + len("        });")
    block = text[first:last]
    assert text.rfind("if (!is_built.load(std::memory_order_acquire)) {", 0, first) >= 0
    assert "if (is_built.load(std::memory_order_acquire)) return;" in block
    assert "std::unique_lock lock{build_mutex};" in block
    assert "build_condvar.wait(lock, [this] { return is_built.load(std::memory_order::relaxed); });" in block
    assert "lock.unlock();" in block
    assert block.index("lock.unlock();") < block.index("pipeline_ready_wait.Stop();") < block.index("keyed_wait.Complete")
    assert 'keyed_wait.Complete("' + kind + '"' in block
    assert "#ifdef PS5_NATIVE" in block and "#endif" in block
    return block

graphics = callback_body(g, "graphics")
compute = callback_body(c, "compute")

cpp = r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <mutex>
#include <optional>
#include <thread>
#include <utility>
using u64 = std::uint64_t;
namespace vk { struct CommandBuffer {}; }
namespace Eden::Performance {
inline std::atomic_bool detailed_gpu_profile{false};
enum class CachePhase { GraphicsPipelineWait, ComputePipelineWait };
struct Timer { ~Timer() {} };
inline std::optional<Timer> VulkanTimer(unsigned) { return std::optional<Timer>{std::in_place}; }
struct CachePhaseTimer {
    explicit CachePhaseTimer(CachePhase, bool) {}
    void Stop() noexcept {}
};
__REAL_TRACE__
}
struct Scheduler {
    std::function<void(vk::CommandBuffer)> callback;
    template<class F> void Record(F&& f) { callback = std::forward<F>(f); }
    void Run() { callback(vk::CommandBuffer{}); }
};
struct Key {
    std::size_t Hash() const noexcept { return 0x1234; }
};
struct Pipeline {
    Scheduler scheduler;
    std::atomic_bool is_built{false};
    std::mutex build_mutex;
    std::condition_variable build_condvar;
    Key key;
    u64 diagnostic_cache_key_hash{0xabcd};
    bool bound{true};
    bool CanExecuteDraw() const {
        return is_built.load(std::memory_order_acquire) && bound;
    }
    bool IsBound() const { return bound; }
    void Queue() {
        if (is_built.load(std::memory_order_acquire)) return;
__ACTUAL_CALLBACK__
    }
    void Publish() {
        { std::lock_guard lock{build_mutex};
          is_built.store(true, std::memory_order_release); }
        build_condvar.notify_all();
    }
};
int main() {
    using Eden::Performance::detailed_gpu_profile;
    // Quiet mode may wait, but must never add a wall-clock log.
    {
        Pipeline quiet;
        quiet.Queue();
        std::thread publisher([&]{ std::this_thread::sleep_for(std::chrono::milliseconds(4)); quiet.Publish(); });
        quiet.scheduler.Run();
        publisher.join();
    }
    detailed_gpu_profile.store(true);
    // Published after Record but before callback -> no actual blocking wait.
    {
        Pipeline already;
        already.Queue();
        already.Publish();
        already.scheduler.Run();
        assert(already.IsBound());
    }
    // Publication really delayed while callback executes.
    {
        Pipeline blocked;
        blocked.Queue();
        std::thread publisher([&] { std::this_thread::sleep_for(std::chrono::milliseconds(6)); blocked.Publish(); });
        blocked.scheduler.Run();
        publisher.join();
    }
    // Failure must still publish and release waiting worker; usable=0.
    {
        Pipeline rejected;
        rejected.bound = false;
        rejected.Queue();
        std::thread publisher([&] { std::this_thread::sleep_for(std::chrono::milliseconds(5)); rejected.Publish(); });
        rejected.scheduler.Run();
        publisher.join();
    }
    detailed_gpu_profile.store(false);
    {
        Pipeline no_work;
        no_work.Publish();
        no_work.Queue();
        assert(!no_work.scheduler.callback);
    }
}
""".replace("__REAL_TRACE__", trace)

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-v01-worker-keyed-") as tmp:
    for kind, callback in (("graphics", graphics), ("compute", compute)):
        source = Path(tmp) / f"{kind}.cpp"
        source.write_text(cpp.replace("__ACTUAL_CALLBACK__", callback))
        for native in (False, True):
            for opt in ("-O0", "-O2"):
                exe = Path(tmp) / f"{kind}-{'ps5' if native else 'desktop'}-{opt[1:]}"
                cmd = [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                       "-pthread", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                       *(["-DPS5_NATIVE=1"] if native else []),
                       str(source), "-o", str(exe)]
                build = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                assert build.returncode == 0, (kind, native, opt, build.stderr[-4000:])
                out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
                assert out.returncode == 0, (kind, native, opt, out.stderr[-3000:])
                lines = [line for line in out.stdout.splitlines()
                         if line.startswith("EDEN_VULKAN_PIPELINE_WAIT ")]
                if native:
                    assert len(lines) == 2, (kind, opt, lines)
                    assert all(f"kind={kind}" in line for line in lines)
                    expected_key = "0000000000001234" if kind == "graphics" else "000000000000abcd"
                    assert all(f"key={expected_key}" in line for line in lines)
                    assert "usable=1" in lines[0]
                    assert "usable=0" in lines[1]
                    assert all(int(line.split("wait_ns=")[1].split()[0]) > 0 for line in lines)
                else:
                    assert not lines, (kind, opt, lines)
                print(f"F07_KEYED_PIPELINE_WAIT_PASS kind={kind} native={int(native)} {opt}")
print("HOST_ONLY no Sony SDK, real GPU worker, FIFO timing in FC27 or frame latency proof")
