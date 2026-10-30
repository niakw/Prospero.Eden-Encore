#!/usr/bin/env python3
"""Source-extracted multi-range retirement replay (native one GPU snapshot).

A GPU completion after the snapshot may be collected next pass. Never free a
tick newer than the sampled completion or change the desktop IsFree path.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-vulkan/vk_multi_range_buffer_cost.cpp").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
fast=(root/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(root/".github/workflows/encore-core-preflight.yml").read_text()
call="python3 -B tools/check-ps5-f07-multirange-retire-snapshot-host.py"
assert call in fast and call in pre
assert "F07 snapshot native multi-range retirement GPU completion once per pass" in generator
begin="void MultiRangeBufferCache::DrainRetired(Scheduler& scheduler) {"
end="\nMultiRangeRef MultiRangeBufferCache::Get("
assert src.count(begin)==1 and src.count(end)==1
real=src[src.index(begin):src.index(end,src.index(begin))]
assert "KnownGpuTick()" in real and "scheduler.IsFree(retired[index].tick)" in real
assert real.index("KnownGpuTick()") < real.index("while (index < retired.size())")
cpp=r"""
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <utility>
#include <vector>
using u64=std::uint64_t;
struct Semaphore {
    u64 completed{};
    unsigned probes{};
    u64 KnownGpuTick(){++probes;return completed;}
};
struct Scheduler {
    Semaphore semaphore{};
    unsigned is_free_probes{};
    Semaphore& GetMasterSemaphore(){return semaphore;}
    bool IsFree(u64 tick) {
        ++is_free_probes;
        return tick<=semaphore.completed;
    }
};
struct Retired {int handle{};u64 tick{};};
struct MultiRangeBufferCache {
    std::vector<Retired> retired{};
    void DrainRetired(Scheduler&);
};
__SOURCE__
int main() {
    Scheduler scheduler;
    MultiRangeBufferCache cache;
    scheduler.semaphore.completed=8;
    cache.DrainRetired(scheduler);
#ifdef PS5_NATIVE
    assert(scheduler.semaphore.probes==0);
#else
    assert(scheduler.is_free_probes==0);
#endif
    cache.retired={{1,2},{2,11},{3,8},{4,5}};
    cache.DrainRetired(scheduler);
    assert(cache.retired.size()==1);
    assert(cache.retired.front().tick==11);
#ifdef PS5_NATIVE
    assert(scheduler.semaphore.probes==1);
    assert(scheduler.is_free_probes==0);
#else
    assert(scheduler.is_free_probes==4);
#endif
    cache.DrainRetired(scheduler);
    assert(cache.retired.size()==1 && cache.retired.front().tick==11);
    scheduler.semaphore.completed=11;
    cache.DrainRetired(scheduler);
    assert(cache.retired.empty());
#ifdef PS5_NATIVE
    assert(scheduler.semaphore.probes==3);
    cache.DrainRetired(scheduler);
    assert(scheduler.semaphore.probes==3);
#endif
}
""".replace("__SOURCE__",real)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 required"
with tempfile.TemporaryDirectory(prefix="f07-retired-snapshot-") as tmp:
    srcfile=Path(tmp)/"main.cpp"
    srcfile.write_text(cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            exe=Path(tmp)/("retire"+opt+str(int(native)))
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                "-fsanitize=undefined","-fno-sanitize-recover=all",
                *(["-DPS5_NATIVE=1"] if native else []),str(srcfile),"-o",str(exe)],
                capture_output=True,text=True,timeout=60)
            assert build.returncode==0,(native,opt,build.stderr[-5000:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-5000:])
print("F07_MULTIRANGE_RETIRE_GPU_SNAPSHOT_PASS native_conservative=1 desktop_original=1 O0_O2=1")
print("F07_NO_PS5_FPS_PROOF")
