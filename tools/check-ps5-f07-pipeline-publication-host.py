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

# Extract the exact graphics and compute wait scheduling snippets. The worker
# command queue is FIFO across chunks, so only one wait per pipeline is needed.
compute_source = (root / "vendor/encore-active/eden-vulkan/vk_compute_pipeline_cost.cpp").read_text()
compute_header = (root / "vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_compute_pipeline.h").read_text()
scheduler_source = (root / "vendor/encore-active/eden-vulkan/vulkan_scheduler.cpp").read_text()
assert "bool first_use_wait_recorded{};" in header
assert "bool first_use_wait_recorded{};" in compute_header
assert "work_queue.push(std::move(chunk));" in scheduler_source
assert "work_queue.front()" in scheduler_source
assert "work->ExecuteAll(current_cmdbuf" in scheduler_source
assert "F07 FIFO once wait graphics start" in generator
assert "F07 FIFO once wait compute start" in generator

def extract_wait(source, function, stop):
    body = source[source.index(function):]
    first = body.index("    if (!is_built.load(std::memory_order_acquire)) {")
    last = body.index(stop, first)
    snippet = body[first:last]
    assert snippet.count("scheduler.Record([this]") == 1
    assert snippet.count("first_use_wait_recorded = true;") == 1
    assert snippet.index("scheduler.Record([this]") < snippet.index("first_use_wait_recorded = true;")
    assert "if (!first_use_wait_recorded)" in snippet
    return snippet

graphics_wait = extract_wait(active, "bool GraphicsPipeline::ConfigureDraw(",
                             "    const bool is_rescaling")
compute_wait = extract_wait(compute_source, "bool ComputePipeline::Configure(",
                            "    // Log compute pipeline binding")
begin = r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <new>
#include <optional>
#include <cstdint>
#include <thread>
#include <utility>
#include <vector>
namespace vk {struct CommandBuffer{};}
namespace Eden::Performance {
enum class CachePhase {GraphicsPipelineWait, ComputePipelineWait};
inline std::atomic_bool detailed_gpu_profile{false};
struct Timer { ~Timer() {} };
std::optional<Timer> VulkanTimer(unsigned) {return std::nullopt;}
struct CachePhaseTimer {CachePhaseTimer(CachePhase,bool){} void Stop() noexcept {} ~CachePhaseTimer(){} };
// Diagnostic semantics are independently exercised by the keyed-wait witness.
struct PipelineWaitTrace {
    // This FIFO test uses a deliberately inert diagnostic. The actual
    // mutex/post-lock timings are compiled from performance.h in the
    // separate keyed-worker-wait source-extracted witness.
    void MarkLockAcquired() noexcept {}
    void Complete(const char*,std::uint64_t,bool) const noexcept {}
};
}
struct Scheduler {
    bool fail_next{};
    std::vector<std::function<void(vk::CommandBuffer)>> jobs;
    template<class F> void Record(F&& f) {
        if(fail_next){fail_next=false;throw std::bad_alloc{};}
        jobs.emplace_back(std::forward<F>(f));
    }
    void Drain(){for(auto& j:jobs)j({});jobs.clear();}
};
struct Key {std::uint64_t Hash() const noexcept {return 0x1234;}};
struct Pipeline {
    Scheduler& scheduler;
    Key key;
    std::uint64_t diagnostic_cache_key_hash{0xabcd};
    bool CanExecuteDraw() const {return is_built.load(std::memory_order_acquire);}
    bool IsBound() const {return is_built.load(std::memory_order_acquire);}
    explicit Pipeline(Scheduler& s):scheduler(s){}
    std::atomic_bool is_built{false};
    std::mutex build_mutex;
    std::condition_variable build_condvar;
#ifdef PS5_NATIVE
    bool first_use_wait_recorded{};
#endif
    void Ready(){
        is_built.store(true,std::memory_order_release);
        build_condvar.notify_all();
    }
"""
end = r"""
};
void Exercise(bool compute){
    Scheduler s;
    Pipeline p{s};
    std::atomic<unsigned> completed{0};
    for(unsigned i=0;i<64;++i){
        if(compute)p.ComputeWait();else p.GraphicsWait();
        s.Record([&](vk::CommandBuffer){
            assert(p.is_built.load(std::memory_order_acquire));
            ++completed;
        });
    }
#ifdef PS5_NATIVE
    assert(s.jobs.size()==65 && p.first_use_wait_recorded);
#else
    assert(s.jobs.size()==128);
#endif
    std::thread execution([&]{s.Drain();});
    std::this_thread::sleep_for(std::chrono::milliseconds(4));
    assert(completed==0);
    p.Ready();
    execution.join();
    assert(completed==64);

    Scheduler retry_scheduler;
    Pipeline retry{retry_scheduler};
    retry_scheduler.fail_next=true;
    bool failed=false;
    try {if(compute)retry.ComputeWait();else retry.GraphicsWait();}
    catch(const std::bad_alloc&){failed=true;}
    assert(failed && retry_scheduler.jobs.empty());
#ifdef PS5_NATIVE
    assert(!retry.first_use_wait_recorded);
#endif
    if(compute)retry.ComputeWait();else retry.GraphicsWait();
    assert(retry_scheduler.jobs.size()==1);
    retry.Ready();retry_scheduler.Drain();

    Scheduler ready_scheduler;
    Pipeline ready{ready_scheduler};
    ready.Ready();
    if(compute)ready.ComputeWait();else ready.GraphicsWait();
    assert(ready_scheduler.jobs.empty());
}
int main(){Exercise(false);Exercise(true);}
"""
fixture = begin + "void GraphicsWait(){\n" + graphics_wait + "}\n" + \
          "void ComputeWait(){\n" + compute_wait + "}\n" + end
with tempfile.TemporaryDirectory(prefix="f07-ordered-wait-") as folder:
    path = Path(folder) / "wait.cpp"
    path.write_text(fixture)
    for definition in ([], ["-DPS5_NATIVE=1"]):
        for mode in ("-O0", "-O2"):
            exe = Path(folder)/("wait-" + ("ps5" if definition else "desktop") + mode[1:])
            built = subprocess.run([compiler,"-std=c++20","-pthread",mode,*definition,
                                    "-Wall","-Wextra","-Werror",str(path),"-o",str(exe)],
                                   capture_output=True,text=True,timeout=50)
            assert built.returncode == 0,(definition,mode,built.stderr[-4000:])
            result = subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert result.returncode == 0,(definition,mode,result.stderr[-4000:])
print("F07_FIFO_ONE_WAIT_HOST_PASS graphics=1 compute=1 native_once=1 desktop_original=1 order=1 enqueue_failure=1 O0=1 O2=1")

print("F07_PIPELINE_PUBLICATION_PASS release_store=1 acquire_reader=2 failed_build=1 O0=1 O2=1")
