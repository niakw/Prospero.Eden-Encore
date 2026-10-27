#!/usr/bin/env python3
"""F07 P0.3: compile shipping compute paired-lock attribution with quiet/verbose gates."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
perf = (root / "headless/performance.h").read_text()
report = (root / "headless/performance.cpp").read_text()
ras = (root / "vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
phases = ("ComputePairWait", "ComputePairHeld", "ComputeConfigure")
names = ("compute_pair_wait", "compute_pair_held", "compute_configure")
for p, n in zip(phases, names):
    assert perf.count(p) == 1, p
    assert report.count('"' + n + '"') == 1, n
    assert ras.count("CachePhase::" + p) == 1, p
    assert p in generator, p
assert "F07 compute paired GPU cache profiling" in generator
start = '    SCOPE_EXIT { SyncProbe(scheduler, "dispatch", pipeline); };'
end = '    const auto& qmd{kepler_compute->launch_description};'
assert ras.count(start) == 1
code = ras[ras.index(start):ras.index(end, ras.index(start))]
assert code.index("compute_pair_wait.Stop();") > code.index("std::scoped_lock lock{")
assert code.index("compute_pair_wait.Stop();") < code.index("CachePhase::ComputePairHeld")
assert code.index("compute_configure.Stop();") > code.index("pipeline->Configure(")
assert "ShouldSampleCacheDraw()" in code
assert "compute_sample" in code

host = r"""
#include <cassert>
#include <chrono>
#include <cstdio>
#include <functional>
#include <mutex>
#include <type_traits>
#include <utility>
struct Maker {};
template<class F> struct Exit { F f; ~Exit(){ f(); } };
template<class F> Exit<std::decay_t<F>> operator+(Maker, F&& f) {
    return {std::forward<F>(f)};
}
#define SCOPE_EXIT auto scope_exit = Maker{} + [&]
struct Cache {
    std::mutex mutex;
};
namespace Eden::Performance {
enum class CachePhase { ComputePairWait, ComputePairHeld, ComputeConfigure };
inline int samples[3]{};
inline int active_timers{};
inline bool diagnostic{};
bool ShouldSampleCacheDraw() { return diagnostic; }
struct CachePhaseTimer {
    int id{};
    bool live{};
    CachePhaseTimer(CachePhase phase, bool enabled) : id(static_cast<int>(phase)), live(enabled) {
        if(live) ++active_timers;
    }
    void Stop() {
        if(!live) return;
        ++samples[id];
        --active_timers;
        live = false;
    }
    ~CachePhaseTimer() { Stop(); }
};
}
struct Pipeline {
    int calls{};
    bool okay{};
    bool Configure(int,int,int,Cache&,Cache&) {
        ++calls;
        return okay;
    }
};
void SyncProbe(int&,const char*,Pipeline*){}
struct Raster {
    Cache texture_cache, buffer_cache;
    Pipeline backing;
    Pipeline* pipeline{&backing};
    int scheduler{};
    int compute{}, memory{};
    int* kepler_compute{&compute};
    int* gpu_memory{&memory};
    void Run(bool succeeds) {
        backing.okay = succeeds;
CODE
    }
};
int main() {
    Raster r;
    Eden::Performance::diagnostic = false;
    r.Run(true);
    assert(r.backing.calls == 1);
    for(auto n : Eden::Performance::samples) assert(n == 0);
    Eden::Performance::diagnostic = true;
    r.Run(true);
    assert(r.backing.calls == 2);
    for(auto n : Eden::Performance::samples) assert(n == 1);
    r.Run(false);
    assert(r.backing.calls == 3);
    for(auto n : Eden::Performance::samples) assert(n == 2);
    assert(Eden::Performance::active_timers == 0);
    std::puts("F07_COMPUTE_PAIR_PROFILE_PASS");
}
"""
host = host.replace("\nCODE\n", "\n" + code)
compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
assert compiler
with tempfile.TemporaryDirectory(prefix="eden-f07-compute-pair-") as temp:
    cpp = Path(temp) / "probe.cpp"
    cpp.write_text(host)
    for opt in ("-O0", "-O2"):
        exe = Path(temp) / opt[1:]
        build = subprocess.run([compiler, "-std=c++20", opt, "-DPS5_NATIVE=1",
                                "-Wall", "-Wextra", "-Werror",
                                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                                str(cpp), "-o", str(exe)], capture_output=True, text=True, timeout=35)
        assert build.returncode == 0, build.stderr
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0 and "F07_COMPUTE_PAIR_PROFILE_PASS" in result.stdout, (result.stdout, result.stderr)
print("F07_COMPUTE_PAIR_PROFILE_HOST_PASS O0=1 O2=1 quiet=1 failure=1")
