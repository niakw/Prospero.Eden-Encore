#!/usr/bin/env python3
"""Source-extracted Vulkan fence completed-tick fast path, compiled ASan/UBSan.

Monotonic timeline progress makes an already signaled fence safe to return
without submitting/awaiting an extra Vulkan semaphore synchronization.
Validates host dispatch counts only, not actual GPU frametimes.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ACTIVE=(ROOT/"vendor/encore-active/eden-vulkan/vk_fence_manager_cost.cpp").read_text()
PIN=(ROOT/"vendor/sources/eden/src/video_core/renderer_vulkan/vk_fence_manager.cpp").read_text()
GEN=(ROOT/"tools/prepare-vulkan-port.py").read_text()
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-vulkan-fence-completed-wait-host.py" in FAST
assert "python3 -B tools/check-vulkan-fence-completed-wait-host.py" in FULL
assert "'vk_fence_manager': [" in GEN
assert "scheduler.IsFree(wait_tick)" in GEN
start="void InnerFence::Wait() {"
end="\n\nFenceManager::FenceManager("
def extract(text):
    assert text.count(start)==1 and text.count(end)==1
    return text[text.index(start):text.index(end,text.index(start))]
native=extract(ACTIVE)
pinned=extract(PIN)
assert "scheduler.IsFree(wait_tick)" in native
assert "scheduler.IsFree(wait_tick)" not in pinned
assert native.count("scheduler.Wait(wait_tick);")==1
cpp=r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
struct Scheduler {
    std::uint64_t completed{};
    mutable unsigned queries{};
    unsigned waits{};
    bool IsFree(std::uint64_t tick) const {
        ++queries;
        return tick<=completed;
    }
    void Wait(std::uint64_t tick) {
        ++waits;
        if(tick>completed)completed=tick;
    }
};
namespace Eden::Performance {
struct VulkanTimer {
    static inline unsigned starts{};
    explicit VulkanTimer(unsigned){++starts;}
};
}
struct InnerFence {
    Scheduler& scheduler;
    bool is_stubbed{};
    std::uint64_t wait_tick{};
    void Wait();
};
INJECT
int main() {
    Scheduler scheduler;
    InnerFence stubbed{scheduler,true,77};
    stubbed.Wait();
    assert(scheduler.waits==0 && scheduler.queries==0);
    InnerFence fence{scheduler,false,7};
    fence.Wait(); // Pending GPU work: must wait and complete the fence.
    assert(scheduler.waits==1 && scheduler.completed==7);
    fence.Wait(); // This used to make a redundant host semaphore call.
    fence.Wait();
    InnerFence already_done{scheduler,false,3};
    already_done.Wait();
    assert(scheduler.waits==EXPECTED_WAITS);
    assert(scheduler.queries==EXPECTED_QUERIES);
    assert(Eden::Performance::VulkanTimer::starts==EXPECTED_TIMERS);
    std::puts("ENCORE_VULKAN_COMPLETED_FENCE_HOST_PASS");
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-vulkan-fence-wait-") as td:
    root=Path(td)
    for name,body,waits,queries,timers in (
        ("pinned",pinned,4,0,0),
        ("native",native,1,4,1),
    ):
        source=root/(name+".cpp")
        exe=root/name
        contents=cpp.replace("INJECT",body)
        contents=contents.replace("EXPECTED_WAITS",str(waits))
        contents=contents.replace("EXPECTED_QUERIES",str(queries))
        contents=contents.replace("EXPECTED_TIMERS",str(timers))
        source.write_text(contents)
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        str(source),"-o",str(exe)],check=True,timeout=90)
        subprocess.run([str(exe)],check=True,timeout=30)
print("VULKAN_COMPLETED_FENCE_HOST_PASS; PS5 GPU wait timing unmeasured")
