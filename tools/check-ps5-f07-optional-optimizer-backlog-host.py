#!/usr/bin/env python3
"""F07 P0.2: source-extracted bounded optional Vulkan optimizer admission.

Execute production queue logic with a controllable one-worker mock at O0/O2.
Verify overflow never queues speculative work, cancellation releases slots,
queue exceptions don't leak reservations and the first-use pipeline remains
valid. No console-frame-time claim.
"""
from pathlib import Path
import ast
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "vendor/encore-active/eden-vulkan/vk_graphics_pipeline_cost.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
fast = (root / ".github/workflows/encore-core-fast-gate.yml").read_text()
pre = (root / ".github/workflows/encore-core-preflight.yml").read_text()
ast.parse(generator)
invocation = "python3 -B tools/check-ps5-f07-optional-optimizer-backlog-host.py"
assert invocation in fast and invocation in pre
for marker in (
    "F07 bound optional Vulkan optimizer queue helper",
    "F07 skip overloaded optional pipeline builds before allocation",
    "F07 release optional pipeline slot on completion or cancellation",
    "F07 hand off optional pipeline slot after successful queue admission",
):
    assert marker in generator, marker
start = "constexpr unsigned kMaxQueuedOptionalOptimizations = 16;"
end = "\n#endif\nCommon::ThreadWorker& OptimizeWorker()"
assert source.count(start) == source.count(end) == 1
slot = source[source.index(start):source.index(end, source.index(start))]
assert slot.count("pending_optional_optimizations.compare_exchange_weak(") == 1
assert slot.count("pending_optional_optimizations{0};") == 1
start = "void GraphicsPipeline::QueueOptimizedPipeline(VkRenderPass render_pass) {"
end = "\nvoid GraphicsPipeline::MakePipeline("
assert source.count(start) == source.count(end) == 1
queue = source[source.index(start):source.index(end, source.index(start))]
assert queue.count("ReserveOptionalOptimizationSlot()") == 1
assert queue.index("ReserveOptionalOptimizationSlot()") < queue.index("std::make_shared<OptimizeState>()")
assert queue.count("pending_optional_optimizations.fetch_sub(1, std::memory_order_release);") == 2
assert queue.index("optional_slot_handed_off = true;") > queue.index("OptimizeWorker().QueueWork(")
assert "if (state->cancelled) return;" in queue
assert "CompletionGuard" in queue
assert "optimized_ready.store(true, std::memory_order_release);" in queue

cpp = r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>
#define LOG_WARNING(...) ((void)0)
using VkRenderPass = int;
using VkPipelineCreateFlags = int;
namespace vk { using Pipeline = int; }
namespace Eden::Performance {
inline void ProbeSchedulerOnce(const char*) {}
}
struct ExitMaker {};
template<class F> struct ExitGuard {
    F f;
    ~ExitGuard() { f(); }
};
template<class F> ExitGuard<std::decay_t<F>> operator+(ExitMaker, F&& f) {
    return {std::forward<F>(f)};
}
#define SCOPE_EXIT auto optional_release_guard = ExitMaker{} + [&]
namespace Common {
class ThreadWorker {
public:
    ThreadWorker(int workers, const char*) { assert(workers == 1); }
    inline static bool reject_next = false;
    std::vector<std::function<void()>> pending;
    template<class F> void QueueWork(F&& f) {
        if (reject_next) {
            reject_next = false;
            throw std::runtime_error("mock queue rejected");
        }
        pending.emplace_back(std::forward<F>(f));
    }
    void RunAll() {
        for (auto& work : pending) work();
        pending.clear();
    }
};
}
namespace Vulkan {
std::atomic<unsigned> pending_first_use_graphics_builds{0};
std::atomic<unsigned> pending_first_use_compute_builds{0};
namespace {
""" + slot + r"""
Common::ThreadWorker& OptimizeWorker() {
    static Common::ThreadWorker worker(1, "VkPipelineOptimize");
    return worker;
}
}
class GraphicsPipeline {
public:
    struct OptimizeState {
        std::mutex mutex;
        std::condition_variable done;
        bool cancelled{false};
        bool running{false};
    };
    std::shared_ptr<OptimizeState> optimize_state;
    int optimized_pipeline{};
    std::atomic_bool optimized_ready{false};
    bool first_use_ready{true};
    void QueueOptimizedPipeline(VkRenderPass);
    void MakePipeline(VkRenderPass pass, VkPipelineCreateFlags, int* target) {
        if (pass == -1) throw std::runtime_error("mock driver failure");
        *target = pass + 10;
    }
};
""" + queue + r"""
}
int main() {
    using namespace Vulkan;
    std::vector<std::unique_ptr<GraphicsPipeline>> pipelines;
    for (unsigned i = 0; i < 40; ++i) {
        auto pipeline = std::make_unique<GraphicsPipeline>();
        pipeline->QueueOptimizedPipeline(5);
        pipelines.push_back(std::move(pipeline));
    }
    assert(pending_optional_optimizations.load() == 16);
    assert(OptimizeWorker().pending.size() == 16);
    for (unsigned i = 0; i < 40; ++i) {
        assert(pipelines[i]->first_use_ready);
        assert(bool(pipelines[i]->optimize_state) == (i < 16));
    }
    for (unsigned i = 0; i < 8; ++i) {
        auto& state = pipelines[i]->optimize_state;
        std::scoped_lock lock{state->mutex};
        state->cancelled = true;
    }
    OptimizeWorker().RunAll();
    assert(pending_optional_optimizations.load() == 0);
    for (unsigned i = 0; i < 40; ++i) {
        const bool should_be_ready = i >= 8 && i < 16;
        assert(pipelines[i]->optimized_ready.load() == should_be_ready);
        if (pipelines[i]->optimize_state)
            assert(!pipelines[i]->optimize_state->running);
    }
    GraphicsPipeline queue_reject;
    Common::ThreadWorker::reject_next = true;
    bool threw = false;
    try { queue_reject.QueueOptimizedPipeline(5); }
    catch (const std::runtime_error&) { threw = true; }
    assert(threw && pending_optional_optimizations.load() == 0);
    assert(queue_reject.optimize_state && !queue_reject.optimize_state->running);

    GraphicsPipeline driver_fails;
    driver_fails.QueueOptimizedPipeline(-1);
    assert(pending_optional_optimizations.load() == 1);
    OptimizeWorker().RunAll();
    assert(pending_optional_optimizations.load() == 0);
    assert(!driver_fails.optimized_ready.load());
    assert(driver_fails.first_use_ready);

    GraphicsPipeline recovered;
    recovered.QueueOptimizedPipeline(8);
    OptimizeWorker().RunAll();
    assert(recovered.optimized_ready.load());
    assert(pending_optional_optimizations.load() == 0);
    assert(recovered.first_use_ready);
}
"""
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-optional-backlog-") as folder:
    source_file = Path(folder) / "optional.cpp"
    source_file.write_text(cpp)
    for optimization in ("-O0", "-O2"):
        executable = Path(folder) / ("optional" + optimization[1:])
        built = subprocess.run(
            [compiler, "-std=c++20", optimization, "-DPS5_NATIVE=1",
             "-Wall", "-Wextra", "-Werror", "-pthread",
             "-fsanitize=undefined", "-fno-sanitize-recover=all",
             str(source_file), "-o", str(executable)],
            capture_output=True, text=True, timeout=60)
        assert built.returncode == 0, (optimization, built.stderr[-5000:])
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
        assert run.returncode == 0, (optimization, run.stdout, run.stderr[-5000:])
print("F07_OPTIONAL_BACKLOG_HOST_PASS max_pending=16 overflow_skipped=24 cancellation=8"
      " reject_no_leak=1 driver_failure=1 reuse=1 O0=1 O2=1")

# The actual first-use builder must survive a rejected *optional* rebuild.
# Extract its precise driver branch and compile the resulting caller.
needle="            if (::Eden::DevVulkan::fast_first_pipelines && fast_first_runtime) {"
assert source.count(needle)==1
b=source.index(needle)
builder=source[b:source.index("            if (pipeline_statistics && pipeline) {",b)]
assert "F07 isolate optional optimizer enqueue rejection from initial pipeline build" in generator
assert builder.index("MakePipeline(render_pass, VK_PIPELINE_CREATE_DISABLE_OPTIMIZATION_BIT)") < builder.index(
    "QueueOptimizedPipeline(render_pass)")
assert "catch (const std::exception& error)" in builder and "catch (...)" in builder
assert builder.count("QueueOptimizedPipeline(render_pass)") == 2
builder_cpp = r"""
#include <cassert>
#include <stdexcept>
#define LOG_WARNING(...) ((void)0)
#define VK_PIPELINE_CREATE_DISABLE_OPTIMIZATION_BIT 1
using VkRenderPass=int;
namespace Eden::DevVulkan {inline bool fast_first_pipelines=true;}
struct FirstUse {
    bool fast_first_runtime=true;
    bool reject_queue=false;
    bool reject_unknown=false;
    bool first_built=false;
    bool collected=false;
    int queued{};
    void MakePipeline(VkRenderPass,int=0) {first_built=true;}
    void QueueOptimizedPipeline(VkRenderPass) {
        ++queued;
        if(reject_unknown)throw 7;
        if(reject_queue)throw std::runtime_error("mock queue rejected");
    }
    void Build(VkRenderPass render_pass) {
""" + builder + r"""
        collected=first_built;
    }
};
int main(){
    for(bool unknown:{false,true}) {
        FirstUse p;p.reject_queue=!unknown;p.reject_unknown=unknown;
#ifdef PS5_NATIVE
        p.Build(1);
        assert(p.first_built&&p.collected&&p.queued==1);
#else
        bool threw=false;
        try{p.Build(1);}catch(...){threw=true;}
        assert(threw&&p.first_built&&!p.collected&&p.queued==1);
#endif
    }
    FirstUse good;good.Build(2);
    assert(good.first_built&&good.collected&&good.queued==1);
    FirstUse direct;direct.fast_first_runtime=false;direct.Build(3);
    assert(direct.first_built&&direct.collected&&direct.queued==0);
}
"""
# A C++ range over {bool,bool} requires initializer_list in both builds.
builder_cpp=builder_cpp.replace("#include <cassert>","#include <cassert>\n#include <initializer_list>")
with tempfile.TemporaryDirectory(prefix="f07-optional-first-use-builder-") as folder:
    p=Path(folder)/"first.cpp"
    p.write_text(builder_cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            exe=Path(folder)/("first"+opt[1:]+("-ps5" if native else "-desktop"))
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror"]
            if native:cmd.append("-DPS5_NATIVE=1")
            built=subprocess.run([*cmd,str(p),"-o",str(exe)],
                                 capture_output=True,text=True,timeout=35)
            assert built.returncode==0,(native,opt,built.stderr[-5000:])
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert ran.returncode==0,(native,opt,ran.stderr[-5000:])
print("F07_OPTIONAL_BUILDER_FAILURE_ISOLATION_PASS first_use_ready=1 reject_known=1 reject_unknown=1 desktop_unchanged=1 O0=1 O2=1")
