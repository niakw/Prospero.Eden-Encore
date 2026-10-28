#!/usr/bin/env python3
"""Check complete first-use compute CPU timing without hot-path clocks."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
perf=(root/"headless/performance.h").read_text()
report=(root/"headless/performance.cpp").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
for f in (".github/workflows/encore-core-fast-gate.yml",
          ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-compute-cold-timing-host.py" in (root/f).read_text()
assert perf.count("ComputePipelineCreate") == 1
assert report.count('"compute_pipeline_create"') == 1
assert "F07 detailed CPU timing for cold compute first use" in gen
assert "F07 detailed CPU timing for delayed compute retry" in gen
start=src.index("ComputePipeline* PipelineCache::CurrentComputePipeline() {")
end=src.index("void PipelineCache::LoadDiskResources(",start)
function=src[start:end]
cold_start=function.index("    if (is_new) {")
cold_end=function.index("        pipeline = CreateComputePipeline(key, shader);",cold_start)
cold=function[cold_start:cold_end+len("        pipeline = CreateComputePipeline(key, shader);")]+"\n    }"
retry_start=function.index("            ::Eden::Performance::CachePhaseTimer retry_compute_cost{")
retry_end=function.index("            pipeline = CreateComputePipeline(key, shader);",retry_start)
retry=function[retry_start:retry_end+len("            pipeline = CreateComputePipeline(key, shader);")]
assert "ComputePipelineCreate" in cold and "ComputePipelineCreate" in retry
assert function.index("failed->second.attempted = true;") < retry_start
assert cold.index("ComputePipelineCreate") < cold.index("CreateComputePipeline(key, shader)")
assert retry.index("ComputePipelineCreate") < retry.index("CreateComputePipeline(key, shader)")
assert function.count("CachePhase::ComputePipelineCreate") == 2
assert "CachePhase::ComputePipelineWait" not in function
cpp=r"""
#include <atomic>
#include <cassert>
namespace Eden::Performance {
enum class CachePhase { ComputePipelineCreate };
inline std::atomic<bool> detailed_gpu_profile{false};
inline unsigned measurements=0;
struct CachePhaseTimer {
    CachePhaseTimer(CachePhase,bool enabled) { if (enabled) ++measurements; }
};
}
struct Key {};
struct Shader {};
unsigned created=0;
int CreateComputePipeline(const Key&,const Shader*) { return ++created; }
void Probe(bool is_new, bool is_retry) {
    // Desktop intentionally has no PS5 retry instrumentation.
    (void)is_retry;
    const Key key{};
    const Shader* shader=nullptr;
    int pipeline=0;
""" + cold + r"""
#ifdef PS5_NATIVE
    if (is_retry) {
""" + retry + r"""
    }
#endif
    (void)pipeline;
}
int main() {
    Probe(false,false);
    assert(created==0 && Eden::Performance::measurements==0);
    Probe(true,false);
    assert(created==1 && Eden::Performance::measurements==0);
    Eden::Performance::detailed_gpu_profile.store(true);
    Probe(false,false);
    assert(created==1 && Eden::Performance::measurements==0);
    Probe(true,false);
    assert(created==2);
#ifdef PS5_NATIVE
    assert(Eden::Performance::measurements==1);
    Probe(false,true);
    assert(created==3 && Eden::Performance::measurements==2);
#else
    assert(Eden::Performance::measurements==0);
    Probe(false,true);
    assert(created==2 && Eden::Performance::measurements==0);
#endif
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler needed"
with tempfile.TemporaryDirectory(prefix="f07-compute-firstuse-") as td:
    source=Path(td)/"timing.cpp"
    source.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            exe=Path(td)/(("native" if native else "desktop")+opt[1:])
            opts=["-DPS5_NATIVE=1"] if native else []
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                                  *opts,str(source),"-o",str(exe)],capture_output=True,text=True,timeout=40)
            assert build.returncode==0,(native,opt,build.stderr[-3000:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-3000:])
print("F07_COMPUTE_COLD_CPU_TIMING_PASS native_cold=1 native_retry=1 no_hot=1 quiet=1 desktop_unchanged=1 O0=1 O2=1")
