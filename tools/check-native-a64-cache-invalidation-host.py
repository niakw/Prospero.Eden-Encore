#!/usr/bin/env python3
"""Compile real default-A64 invalidation handler for quiet/release/DEV.

Observes only successful application (full clear vs range batch), while
checking cache owner and RSB/halt behavior in both compilation profiles.
No simulated PS5 framerate or shared-JIT path.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
A64=(ROOT/"vendor/encore-active/eden-core/src/dynarmic/backend/x64/a64_interface_standard.cpp").read_text()
PERF=(ROOT/"headless/performance.cpp").read_text()
PERFH=(ROOT/"headless/performance.h").read_text()
MAIN=(ROOT/"headless/main.cpp").read_text()
start=A64.index("    void PerformRequestedCacheInvalidation(HaltReason hr) {")
end=A64.index("\n    IR::Block ir_block", start)
snippet=A64[start:end].rstrip()
assert '#if defined(EDEN_JIT_A64_DEV_PROFILE)' in snippet
assert 'clear_all ? 0u : 1u' in snippet
assert 'eden_native_detailed_logging() &&' in snippet
assert 'eden_jit_cache_event' in snippet
assert 'std::unique_lock lock{invalidation_mutex};' in snippet
assert 'block_of_code.ClearCache();' in snippet
assert 'emitter.ClearCache();' in snippet
assert 'emitter.InvalidateCacheRanges(ranges);' in snippet
assert 'ranges.swap(invalid_cache_ranges);' in snippet
assert 'invalid_cache_ranges.clear();' not in snippet
assert snippet.index('ranges.swap(invalid_cache_ranges);') < snippet.index('emitter.InvalidateCacheRanges(ranges);')
assert 'jit_state.ResetRSB();' in snippet
assert 'extern "C" void eden_jit_cache_event(unsigned core, unsigned kind)' in PERF
assert 'EDEN_PERF_JIT_CACHE mono_ns=' in PERF
assert "jit_cache_events[core][kind].fetch_add(" in PERF
assert "for (auto& core : jit_cache_events)" in PERF
assert 'inline std::array<std::array<std::atomic<unsigned long long>, 2>, 4> jit_cache_events' in PERFH
assert 'Eden::Performance::ResetJitDuplicateTrackingForTitle();' in MAIN

CPP=r"""
#include <cassert>
#include <cstdint>
#include <mutex>
#include <cstdio>
using u64 = std::uint64_t;
enum class HaltReason { None=0, CacheInvalidation=1 };
bool Has(HaltReason given, HaltReason expected) { return given == expected; }
static bool detailed=false;
static unsigned reports[2]{};
static unsigned bad_core=0;
extern "C" bool eden_native_detailed_logging() noexcept __attribute__((weak));
extern "C" bool eden_native_detailed_logging() noexcept { return detailed; }
extern "C" void eden_jit_cache_event(unsigned,unsigned) __attribute__((weak));
extern "C" void eden_jit_cache_event(unsigned core,unsigned kind) {
    if (core!=2 || kind>1) { ++bad_core; return; }
    ++reports[kind];
}
struct Ranges {
    bool present=false;
    bool empty() const { return !present; }
    void clear() { present=false; }
    void swap(Ranges& other) { const bool original=present; present=other.present; other.present=original; }
};
namespace boost::icl {
template<class T> using interval_set = ::Ranges;
}
struct Code {
    int cleared=0;
    void ClearCache() { ++cleared; }
};
struct Emitter {
    int cleared=0, ranged=0;
    void ClearCache() { ++cleared; }
    void InvalidateCacheRanges(const Ranges& r) { assert(r.present); ++ranged; }
};
struct State {
    int rsb_resets=0;
    void ResetRSB() { ++rsb_resets; }
};
struct Conf { unsigned processor_id=2; };
struct Probe {
    std::mutex invalidation_mutex;
    bool invalidate_entire_cache=false;
    Ranges invalid_cache_ranges;
    Code block_of_code;
    Emitter emitter;
    State jit_state;
    Conf conf;
    int halts_cleared=0;
    void ClearHalt(HaltReason) { ++halts_cleared; }
INJECT
};
int main() {
    Probe p;
    p.PerformRequestedCacheInvalidation(HaltReason::None);
    assert(p.halts_cleared == 0 && !reports[0] && !reports[1]);
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.halts_cleared == 1 && p.jit_state.rsb_resets == 0);
    detailed=true;
    p.invalid_cache_ranges.present=true;
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.jit_state.rsb_resets == 1 && p.emitter.ranged == 1 &&
           !p.invalid_cache_ranges.present && p.block_of_code.cleared == 0);
    p.invalid_cache_ranges.present=true;
    p.invalidate_entire_cache=true;
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.jit_state.rsb_resets == 2 && p.block_of_code.cleared == 1 &&
           p.emitter.cleared == 1 && p.emitter.ranged == 1 &&
           !p.invalid_cache_ranges.present && !p.invalidate_entire_cache);
#if defined(EDEN_JIT_A64_DEV_PROFILE)
    assert(reports[0] == 1 && reports[1] == 1);
#else
    assert(reports[0] == 0 && reports[1] == 0);
#endif
    detailed=false;
    p.invalid_cache_ranges.present=true;
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.emitter.ranged == 2 && p.jit_state.rsb_resets == 3);
#if defined(EDEN_JIT_A64_DEV_PROFILE)
    assert(reports[0] == 1 && reports[1] == 1);
#endif
    assert(bad_core == 0);
    std::puts("ENCORE_DEFAULT_A64_JIT_CACHE_EVENTS_PASS");
}
""".replace("INJECT",snippet)
compiler=os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-default-jit-cache-") as tmp:
    d=Path(tmp)
    source=d/"test.cpp"
    source.write_text(CPP)
    for variant,flags in (("release",[]),("dev",["-DEDEN_JIT_A64_DEV_PROFILE=1"])):
        exe=d/variant
        subprocess.run(
            [compiler,"-std=c++20","-O1","-Wall","-Wextra",
             "-fsanitize=address,undefined","-fno-sanitize-recover=all",
             *flags,str(source),"-o",str(exe)],
            check=True,timeout=90,capture_output=True,text=True)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
        assert result.returncode==0,(variant,result.stdout[-1000:],result.stderr[-2000:])
print("ENCORE_A64_CACHE_INVALIDATION_HOST_PASS source_extracted=1 dev=1 release=1 quiet=1")
