#!/usr/bin/env python3
"""ASan/UBSan host witness for a cheaper GPU fence completion publication.

Compiles the exact store and acquire-load expressions from BOTH tracked GPU
worker variants, exercising ordered per-command payload publication. The
original pinned seq_cst store is the baseline. This is not an FPS benchmark,
not TSAN, and cannot certify PS5 GPU progress or device fences.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL=(ROOT/"vendor/sources/eden/src/video_core/gpu_thread.cpp").read_text()
QUIET=(ROOT/"vendor/encore-active/eden-gpu/gpu_thread_quiet.cpp").read_text()
DEV=(ROOT/"vendor/encore-active/eden-gpu/gpu_thread_dev.cpp").read_text()
HEADER=(ROOT/"vendor/encore-active/eden-gpu/include/video_core/gpu_thread.h").read_text()
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
SCRIPT="python3 -B tools/check-native-gpu-fence-release-publication-host.py"
assert SCRIPT in FAST and SCRIPT in FULL
assert "std::atomic<u64> signaled_fence" in HEADER
PIN="state.signaled_fence.store(next.fence);"
OPT="state.signaled_fence.store(next.fence, std::memory_order_release);"
CONSUME="state.signaled_fence.load(std::memory_order_acquire)"
assert ORIGINAL.count(PIN)==1
assert QUIET.count(OPT)==DEV.count(OPT)==1
assert QUIET.count(PIN)==DEV.count(PIN)==0
assert QUIET.count(CONSUME)==DEV.count(CONSUME)==2
assert QUIET.count("state.cv.notify_all();")==DEV.count("state.cv.notify_all();")==1
assert QUIET.index(OPT)<QUIET.index("state.cv.notify_all();")
assert DEV.index(OPT)<DEV.index("state.cv.notify_all();")
assert QUIET.count("std::memory_order_release")>=1
assert DEV.count("std::memory_order_release")>=1
assert "gpu_thread_quiet.cpp" in (ROOT/"headless/CMakeLists.txt").read_text()
assert "gpu_thread_dev.cpp" in (ROOT/"headless/CMakeLists.txt").read_text()

cpp=r"""
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <thread>
#include <vector>
using u64=std::uint64_t;
struct SynchState { std::atomic<u64> signaled_fence{}; };
struct Next { u64 fence{}; };
int main() {
    constexpr u64 limit=32768;
    std::vector<u64> payload(limit+1);
    SynchState state;
    std::thread worker([&] {
        Next next;
        for(u64 i=1;i<=limit;++i) {
            payload[i]=i^0x5a5a5a5aULL;
            next.fence=i;
            WRITE_EXPRESSION
        }
    });
    u64 inspected=0;
    while(inspected<limit) {
        // This is the actual maintained GPU PushCommand acquire expression.
        const u64 completed=READ_EXPRESSION;
        assert(completed<=limit);
        while(inspected<completed) {
            ++inspected;
            assert(payload[inspected]==(inspected^0x5a5a5a5aULL));
        }
        if (inspected<limit) std::this_thread::yield();
    }
    worker.join();
    assert(state.signaled_fence.load(std::memory_order_acquire)==limit);
    std::printf("GPU_FENCE_RELEASE_PUBLICATION_PASS commands=%llu\n",
                static_cast<unsigned long long>(limit));
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"missing C++20 compiler"
with tempfile.TemporaryDirectory(prefix="encore-fence-release-") as tmp:
    for name,publication in (("upstream",PIN),("quiet",OPT),("dev",OPT)):
        target=Path(tmp)/(name+".cpp")
        output=Path(tmp)/name
        target.write_text(cpp.replace("WRITE_EXPRESSION",publication)
                             .replace("READ_EXPRESSION",CONSUME))
        subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra",
                        "-Werror","-pthread","-fsanitize=address,undefined",
                        "-fno-sanitize-recover=all",str(target),"-o",str(output)],
                       check=True,timeout=90)
        subprocess.run([str(output)],check=True,timeout=45)
print("GPU_FENCE_RELEASE_HOST_PASS native_modes=quiet,dev publisher=release reader=acquire; ps5_fps=unknown")
