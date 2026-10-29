#!/usr/bin/env python3
"""S01: compile actual per-key cold-shader phase timer and RAII attribution.

Host-only test. Native mode changes diagnostic attribution, not CPU scheduling,
Vulkan worker fences, shader outputs, or the quiet path.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
perf = (root / "headless/performance.h").read_text()
pipeline = (root / "vendor/encore-active/eden-vulkan/vk_pipeline_cache_cost.cpp").read_text()
gen = (root / "tools/prepare-vulkan-port.py").read_text()
analyzer = (root / "tools/analyze-ps5-cold-shader-misses.py").read_text()

stage_start = perf.index("struct ShaderMissStageCosts {")
stage_end = perf.index("inline thread_local ShaderMissStageCosts* shader_miss_stage_active{};", stage_start)
stage_end += len("inline thread_local ShaderMissStageCosts* shader_miss_stage_active{};")
stage_declarations = perf[stage_start:stage_end]
timer_start = perf.index("class CachePhaseTimer {")
timer_end = perf.index("\n};", timer_start) + len("\n};")
real_timer = perf[timer_start:timer_end]
trace_start = pipeline.index("struct ColdShaderMissTrace {")
trace_end = pipeline.index("\n};\n#endif", trace_start) + len("\n};")
real_trace = pipeline[trace_start:trace_end]

assert real_trace in gen
assert "shader_miss_stage_active" in real_trace
assert "if (!enabled) return;" in real_trace
assert "std::chrono::steady_clock::now()" in real_trace
assert "shader_miss_stage_active = previous;" in real_trace
assert "EDEN_VULKAN_SHADER_MISS kind=%s key=%016llx" in real_trace
assert "env_ns=%llu pool_ns=%llu" in real_trace
assert "cfg_ns=%llu ir_ns=%llu spirv_ns=%llu module_ns=%llu" in real_trace
assert "phase(phase)" in real_timer
assert "if (auto* const keyed = shader_miss_stage_active)" in real_timer
for name in ("GraphicsShaderEnvironment", "ShaderPoolReset", "ShaderCfg", "ShaderIr",
             "ShaderSpirv", "ShaderModule"):
    assert "case CachePhase::" + name + ":" in real_timer, name
assert "stats->total_ns.fetch_add(ns, std::memory_order_relaxed);" in real_timer
assert "std::chrono::steady_clock::time_point" in real_trace
assert "stages: tuple[int, int, int, int, int, int] | None = None" in analyzer

cpp = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstdint>
#include <stdexcept>
#include <string>
using u64 = std::uint64_t;

namespace Common {
struct FakeClock {
    std::chrono::nanoseconds now{};
    [[nodiscard]] std::chrono::nanoseconds GetTimeNS() const { return now; }
};
inline FakeClock g_wall_clock;
}
namespace Eden::Performance {
enum class CachePhase : unsigned {
    GraphicsShaderEnvironment, ShaderPoolReset, ShaderCfg, ShaderIr,
    ShaderSpirv, ShaderModule, Other, Count
};
struct CachePhaseTotal {
    std::atomic<unsigned long long> samples{}, total_ns{}, max_ns{};
};
inline std::array<CachePhaseTotal, static_cast<unsigned>(CachePhase::Count)> cache_phase_totals{};
inline thread_local bool cache_draw_sample_active = false;
inline std::atomic<bool> detailed_gpu_profile{false};
__STAGE_DECLARATIONS__
__REAL_TIMER__
}

#ifdef PS5_NATIVE
__REAL_TRACE__
#endif
void Stage(Eden::Performance::CachePhase phase, unsigned long long nanos) {
    Eden::Performance::CachePhaseTimer timer{phase, true};
    Common::g_wall_clock.now += std::chrono::nanoseconds(nanos);
    timer.Stop();
}
int main() {
    using namespace Eden::Performance;
#ifdef PS5_NATIVE
    // No session owner with quiet logging, even though the hot shader is
    // created. Unkeyed sampled phases must continue to work independently.
    {
        ColdShaderMissTrace quiet{"graphics", 1, false};
        assert(shader_miss_stage_active == nullptr);
        Stage(CachePhase::ShaderCfg, 2);
        quiet.Complete(true);
    }
    detailed_gpu_profile.store(true);
    {
        ColdShaderMissTrace cold{"graphics", 2, false};
        assert(shader_miss_stage_active == &cold.stages);
        Stage(CachePhase::GraphicsShaderEnvironment, 3);
        Stage(CachePhase::ShaderPoolReset, 5);
        Stage(CachePhase::ShaderCfg, 7);
        Stage(CachePhase::ShaderIr, 11);
        Stage(CachePhase::ShaderSpirv, 13);
        Stage(CachePhase::ShaderModule, 17);
        Stage(CachePhase::Other, 19);
        assert(cold.stages.env_ns == 3 && cold.stages.pool_ns == 5);
        assert(cold.stages.cfg_ns == 7 && cold.stages.ir_ns == 11);
        assert(cold.stages.spirv_ns == 13 && cold.stages.module_ns == 17);
        {
            ColdShaderMissTrace nested{"compute", 3, true};
            assert(shader_miss_stage_active == &nested.stages);
            Stage(CachePhase::ShaderCfg, 23);
            assert(nested.stages.cfg_ns == 23);
            assert(cold.stages.cfg_ns == 7);
            nested.Complete(false);
        }
        assert(shader_miss_stage_active == &cold.stages);
        Stage(CachePhase::ShaderCfg, 29);
        assert(cold.stages.cfg_ns == 36);
        cold.Complete(true);
        assert(shader_miss_stage_active == nullptr);
        Stage(CachePhase::ShaderModule, 31); // not part of the completed miss
        assert(cold.stages.module_ns == 17);
    }
    {
        ColdShaderMissTrace retry{"graphics", 4, true};
        Stage(CachePhase::ShaderModule, 37);
        retry.Complete(true);
        assert(retry.stages.module_ns == 37);
    }
    assert(shader_miss_stage_active == nullptr);
    try {
        ColdShaderMissTrace error{"compute", 5, false};
        Stage(CachePhase::ShaderIr, 41);
        throw std::runtime_error("exception within a cold translation");
    } catch (const std::runtime_error&) {
        assert(shader_miss_stage_active == nullptr);
    }
    detailed_gpu_profile.store(false);
    {
        ColdShaderMissTrace quiet_again{"compute", 6, true};
        assert(shader_miss_stage_active == nullptr);
        quiet_again.Complete(false);
    }
#else
    Stage(CachePhase::ShaderCfg, 2);
    assert(shader_miss_stage_active == nullptr);
#endif
    assert(cache_phase_totals[static_cast<unsigned>(CachePhase::ShaderCfg)]
               .samples.load() >= 1);
}
"""
cpp = cpp.replace("__STAGE_DECLARATIONS__", stage_declarations)
cpp = cpp.replace("__REAL_TIMER__", real_timer)
cpp = cpp.replace("__REAL_TRACE__", real_trace)

compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-keyed-shader-stages-") as temp:
    src = Path(temp) / "probe.cpp"
    src.write_text(cpp)
    for native in (False, True):
        for opt in ("-O0", "-O2"):
            exe = Path(temp) / ("ps5" if native else "desktop") / opt[1:]
            exe.parent.mkdir(exist_ok=True)
            build = subprocess.run(
                [compiler, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 *(["-DPS5_NATIVE=1"] if native else []),
                 str(src), "-o", str(exe)], capture_output=True, text=True, timeout=45
            )
            assert build.returncode == 0, (native, opt, build.stderr[-6000:])
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            assert run.returncode == 0, (native, opt, run.stdout, run.stderr[-4000:])
            if native:
                assert run.stdout.count("EDEN_VULKAN_SHADER_MISS") == 3
                assert "key=0000000000000002" in run.stdout
                assert "env_ns=3 pool_ns=5 cfg_ns=36 ir_ns=11 spirv_ns=13 module_ns=17" in run.stdout
                assert "key=0000000000000003" in run.stdout
                assert "cfg_ns=23" in run.stdout
                assert "key=0000000000000004" in run.stdout
                assert "module_ns=37" in run.stdout
                assert "key=0000000000000001" not in run.stdout
                assert "key=0000000000000005" not in run.stdout
                assert "key=0000000000000006" not in run.stdout
            else:
                assert "EDEN_VULKAN_SHADER_MISS" not in run.stdout
            print(f"F07_KEYED_SHADER_STAGES_PASS mode={'PS5' if native else 'desktop'} {opt}")
print("HOST_ONLY no shader output, Vulkan worker, FPS or console measurements")
