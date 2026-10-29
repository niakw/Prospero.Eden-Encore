#!/usr/bin/env python3
"""Native Vulkan per-buffer GPU usage retirement; source-extracted O0/O2 UBSan."""
import ast
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
active=(ROOT/"vendor/encore-active/eden-vulkan/vk_buffer_cache_cost.cpp").read_text()
pinned=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_buffer_cache.h").read_text()
generator=(ROOT/"tools/prepare-vulkan-port.py").read_text()
tree=ast.parse(generator)
header_replacements=[]
for statement in tree.body:
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        continue
    node=statement.value
    if not isinstance(node.func,ast.Name) or node.func.id!="adapt" or len(node.args)!=3:
        continue
    try:
        name=ast.literal_eval(node.args[0])
        dest=ast.literal_eval(node.args[1])
    except (ValueError,TypeError):
        continue
    if name=="src/video_core/renderer_vulkan/vk_buffer_cache.h":
        assert dest=="include/video_core/renderer_vulkan/vk_buffer_cache.h"
        header_replacements=ast.literal_eval(node.args[2])
assert len(header_replacements)==1
old, new=header_replacements[0]
assert old in pinned and pinned.count(old)==1
assert "last_usage_tick = 0;" in new and "#ifdef PS5_NATIVE" in new
header=pinned.replace(old,new)
# The selected shipping Vulkan fork must contain the same native header
# replayed from the installed Eden backport (not merely a test-only mock).
backport=(ROOT/"vendor/encore-active/eden-backports/src/video_core/renderer_vulkan/vk_buffer_cache.h").read_text()
maintained=(ROOT/"vendor/encore-active/eden-vulkan/include/video_core/renderer_vulkan/vk_buffer_cache.h").read_text()
assert backport.count(old)==1
assert maintained==backport.replace(old,new)
start=header.index("    void ResetUsageTracking() noexcept {")
stop=header.index("    [[nodiscard]] u64 LastUsageTick()",start)
reset=header[start:stop].strip()
assert "#ifdef PS5_NATIVE" in reset
runtime_start="void BufferCacheRuntime::TickFrame("
runtime_end="\nu64 BufferCacheRuntime::CurrentTick()"
assert active.count(runtime_start)==active.count(runtime_end)==1
method=active[active.index(runtime_start):active.index(runtime_end,active.index(runtime_start))]
assert "if (last_tick <= completed_tick)" in method
assert "if (last_tick == 0)" in method
assert "sampled_completed_tick" in method
assert "scheduler.GetMasterSemaphore().KnownGpuTick()" in method
for workflow in ("encore-core-fast-gate.yml","encore-core-preflight.yml"):
    assert "check-vulkan-buffer-usage-reset-host.py" in (ROOT/".github/workflows"/workflow).read_text()
cpp=r"""
#include <cassert>
#include <cstdint>
#include <vector>
using u64=std::uint64_t;
namespace Common {template<typename T>struct SlotVector:std::vector<T>{};}
struct Tracker {
    int resets{};
    bool active{};
    void Reset() {++resets;active=false;}
};
struct Buffer {
    Tracker tracker{};
    u64 last_usage_tick{};
__RESET__
    u64 LastUsageTick() const noexcept {return last_usage_tick;}
    void MarkUsage(u64 tick){tracker.active=true;last_usage_tick=tick;}
};
struct MasterSemaphore {
    u64 completed{};
    int samples{};
    u64 KnownGpuTick(){++samples;return completed;}
};
struct Scheduler {
    MasterSemaphore& sem;
    MasterSemaphore& GetMasterSemaphore(){return sem;}
};
struct BufferCacheRuntime {
    Scheduler& scheduler;
    void TickFrame(Common::SlotVector<Buffer>&) noexcept;
};
__TICK__
int main(){
    MasterSemaphore semaphore{15,0};
    Scheduler scheduler{semaphore};
    BufferCacheRuntime runtime{scheduler};
    Common::SlotVector<Buffer> buffers;
    buffers.resize(3);
    buffers[0].last_usage_tick=0; // idle from construction
    buffers[1].MarkUsage(10);
    buffers[2].MarkUsage(20);
    runtime.TickFrame(buffers);
    assert(semaphore.samples==1);
    assert(!buffers[1].tracker.active && buffers[1].tracker.resets==1);
    assert(buffers[2].tracker.active && buffers[2].tracker.resets==0);
#ifdef PS5_NATIVE
    assert(buffers[0].tracker.resets==0);
    assert(buffers[1].last_usage_tick==0);
#endif
    runtime.TickFrame(buffers);
#ifdef PS5_NATIVE
    assert(buffers[0].tracker.resets==0 && buffers[1].tracker.resets==1);
#else
    assert(buffers[0].tracker.resets==2 && buffers[1].tracker.resets==2);
#endif
    assert(buffers[2].tracker.resets==0);
    semaphore.completed=20;
    runtime.TickFrame(buffers);
    assert(!buffers[2].tracker.active && buffers[2].tracker.resets==1);
    buffers[1].MarkUsage(25); // reactivation must reset on NEXT completion
    runtime.TickFrame(buffers);
#ifdef PS5_NATIVE
    assert(buffers[1].tracker.active && buffers[1].tracker.resets==1);
#endif
    semaphore.completed=25;
    runtime.TickFrame(buffers);
#ifdef PS5_NATIVE
    assert(!buffers[1].tracker.active && buffers[1].tracker.resets==2);
    assert(buffers[1].last_usage_tick==0);
    assert(buffers[2].tracker.resets==1);
    // All buffers are now retired; no outstanding GPU work merits polling.
    const auto sampled=semaphore.samples;
    runtime.TickFrame(buffers);
    assert(semaphore.samples==sampled);
#else
    assert(!buffers[1].tracker.active && buffers[1].tracker.resets==4);
#endif
}
""".replace("__RESET__",reset).replace("__TICK__",method)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-vulkan-buffer-reset-") as d:
    source=Path(d)/"runtime.cpp"
    source.write_text(cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            out=Path(d)/f"runtime-{native}-{opt}"
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(['-DPS5_NATIVE=1'] if native else []),str(source),"-o",str(out)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
            assert built.returncode==0,(native,opt,built.stderr[-3000:])
            run=subprocess.run([str(out)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-3000:])
print("F07_BUFFER_USAGE_RESET_PASS O0=1 O2=1 native_retires_once=1 idle_skip_gpu_probe=1 reactivation=1 desktop_original=1")
