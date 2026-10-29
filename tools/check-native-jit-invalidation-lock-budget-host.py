#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F02: pinned-vs-selected A32/A64 real invalidation-method lock budgets.

Compile the actual historical and maintained source-derived C++ range
invalidation and drain methods. Compare lock-held duration on an identical
synthetic emitter workload with a real competing lock owner, cold requests,
repeat-empty drains and a subsequent invalidation. This is NOT compilation
latency, native PS5 timing, or a fully-qualified F02 exit gate.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
HEADLESS=(ROOT/"headless/CMakeLists.txt").read_text()
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
CMD="python3 -B tools/check-native-jit-invalidation-lock-budget-host.py"
assert CMD in FAST and CMD in FULL
assert "a64_interface_standard.cpp" in HEADLESS
assert "a32_interface_native.cpp" in HEADLESS
assert "EDEN_A64_INTERFACE_UNIT" in HEADLESS
assert 'EDEN_SHARED_JIT OR EDEN_JIT_COMPILE_BATCH' in HEADLESS
# F02's default native profile uses direct per-core code, not opt-in batch.
assert 'option(EDEN_JIT_COMPILE_BATCH "Compile bounded A64 successor chains on a cache miss" OFF)' in HEADLESS
ARCHES={
 "A32":(
    "vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/a32_interface.cpp",
    "vendor/encore-active/eden-core/src/dynarmic/backend/x64/a32_interface_native.cpp","u32"),
 "A64":(
    "vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/a64_interface.cpp",
    "vendor/encore-active/eden-core/src/dynarmic/backend/x64/a64_interface_standard.cpp","u64"),
}
def extract(source:str,signature:str)->str:
    assert source.count(signature)==1,signature
    begin=source.index(signature)
    opening=source.index("{",begin)
    depth=0
    for i in range(opening,len(source)):
        if source[i]=="{":depth+=1
        elif source[i]=="}":
            depth-=1
            if depth==0:return source[begin:i+1]
    raise AssertionError(signature)
TEMPLATE=r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <limits>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>
using u32=std::uint32_t;
using u64=std::uint64_t;
using Address=ADDRESS;
using Clock=std::chrono::steady_clock;
enum class HaltReason {None,CacheInvalidation};
bool Has(HaltReason a,HaltReason b){return a==b;}
namespace boost::icl {
template<typename T> struct discrete_interval {
    T lo{},hi{};
    static discrete_interval closed(T a,T b){return {a,b};}
};
template<typename T> struct interval_set {
    std::vector<discrete_interval<T>> spans;
    bool empty()const{return spans.empty();}
    void clear(){spans.clear();}
    void swap(interval_set& that){spans.swap(that.spans);}
    void add(discrete_interval<T> item){spans.push_back(item);}
};
}
struct TimedMutex {
    static thread_local unsigned depth;
    std::mutex mutex;
    std::atomic<u64> held_ns{0};
    std::atomic<u64> gets{0};
    Clock::time_point entered{};
    void lock() {
        mutex.lock();++depth;entered=Clock::now();
        gets.fetch_add(1,std::memory_order_relaxed);
    }
    void unlock() {
        const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(
            Clock::now()-entered).count();
        held_ns.fetch_add(static_cast<u64>(ns),std::memory_order_relaxed);
        --depth;mutex.unlock();
    }
    bool try_lock() {
        if(!mutex.try_lock())return false;
        ++depth;entered=Clock::now();
        gets.fetch_add(1,std::memory_order_relaxed);
        return true;
    }
};
thread_local unsigned TimedMutex::depth=0;
struct State {unsigned resets{};void ResetRSB(){++resets;}};
struct Code {
    unsigned cleared{};
    void ClearCache(){++cleared;}
};
struct Emitter {
    unsigned ranged{},cleared{},last_count{};
    std::atomic<u64> workload{0};
    TimedMutex* tracked{};
    bool executed_under_guard{};
    void InvalidateCacheRanges(const boost::icl::interval_set<Address>& spans){
        ++ranged;
        last_count=static_cast<unsigned>(spans.spans.size());
        assert(last_count==1);
        // try_lock from the owning thread on a non-recursive std::mutex is
        // undefined; track THIS thread's lock ownership explicitly.
        if (TimedMutex::depth) executed_under_guard=true;
        u64 v=static_cast<u64>(spans.spans[0].lo)+static_cast<u64>(spans.spans[0].hi);
        // Identical deterministic synthetic emitter cost for pinned/maintained.
        for(unsigned i=0;i<4096;++i)
            v=(v*1664525ULL+1013904223ULL)^(v>>7);
        workload.fetch_add(v,std::memory_order_relaxed);
    }
    void ClearCache(){++cleared;}
};
struct Probe {
    TimedMutex invalidation_mutex;
    boost::icl::interval_set<Address> invalid_cache_ranges;
    bool invalidate_entire_cache{};
    unsigned halts{},cleared_halts{};
    State jit_state;
    Code block_of_code;
    Emitter emitter;
    Probe(){emitter.tracked=&invalidation_mutex;}
    void HaltExecution(HaltReason){++halts;}
    void ClearHalt(HaltReason){++cleared_halts;}
    void InvalidateCacheRange(Address,size_t);
    void PerformRequestedCacheInvalidation(HaltReason);
};
__RANGE__
__APPLY__
int main(){
    Probe p;
    constexpr unsigned iterations=96;
    unsigned empty_repeats{};
    std::atomic<bool> running{true};
    std::atomic<unsigned> competitor_gets{};
    // Start the measured invalidation burst only AFTER the real competing
    // thread has acquired/released the mutex once. Without a handshake, a
    // fast -O2 source replay can finish all 96 drains before that thread is
    // ever scheduled; that is not evidence of a lock-budget regression.
    std::atomic<bool> competitor_started{false};
    std::thread competitor([&] {
        while(running.load(std::memory_order_relaxed)){
            {
                std::lock_guard<TimedMutex> lk{p.invalidation_mutex};
                ++competitor_gets;
            }
            if (!competitor_started.exchange(true,std::memory_order_release)) {
                competitor_started.notify_one();
            }
            std::this_thread::yield();
        }
    });
    competitor_started.wait(false,std::memory_order_acquire);
    assert(competitor_gets.load(std::memory_order_acquire)>0);
    for(unsigned i=0;i<iterations;++i){
        p.InvalidateCacheRange(static_cast<Address>(0x1000+i*8),4);
        p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
        p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
        ++empty_repeats;
    }
    running.store(false,std::memory_order_relaxed);
    competitor.join();
    assert(p.emitter.ranged==iterations);
    assert(p.jit_state.resets==iterations);
    assert(p.emitter.cleared==0);
    assert(p.emitter.workload.load(std::memory_order_relaxed)!=0);
    assert(empty_repeats==iterations);
    assert(competitor_started.load(std::memory_order_acquire));
    assert(competitor_gets.load(std::memory_order_acquire)>0);
    // The maintained code dispatches outside mutex; old code does not.
    assert(p.emitter.executed_under_guard==PINNED_EXPECTED);
    const auto held=p.invalidation_mutex.held_ns.load(std::memory_order_relaxed);
    assert(held>0);
    std::printf("F02_JIT_NATIVE_INVALIDATION_BUDGET_PASS arch=ARCH "
                "impl=IMPL range_drains=%u empty_repeats=%u "
                "held_lock_ns=%llu pinned_dispatch_under_guard=%u "
                "scope=source_extracted_synthetic_emitter\n",
                p.emitter.ranged,empty_repeats,
                static_cast<unsigned long long>(held),
                unsigned(p.emitter.executed_under_guard));
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f02-invalidate-") as folder:
    for arch,(pin,active,typ) in ARCHES.items():
        pinned=(ROOT/pin).read_text()
        selected=(ROOT/active).read_text()
        for impl,src in (("pinned",pinned),("maintained",selected)):
            rng=extract(src,"    void InvalidateCacheRange(")
            apply=extract(src,"    void PerformRequestedCacheInvalidation(")
            if impl=="pinned":
                assert "ranges.swap(invalid_cache_ranges)" not in apply
                assert "std::unique_lock lock{invalidation_mutex}" in apply
            else:
                assert "ranges.swap(invalid_cache_ranges)" in apply
                assert apply.index("ranges.swap(invalid_cache_ranges)") < apply.index("emitter.InvalidateCacheRanges(ranges)")
                assert "std::unique_lock lock{invalidation_mutex}" in apply
            rng=rng.replace("    void InvalidateCacheRange(","void Probe::InvalidateCacheRange(",1)
            apply=apply.replace("    void PerformRequestedCacheInvalidation(","void Probe::PerformRequestedCacheInvalidation(",1)
            cpp=TEMPLATE.replace("__RANGE__",rng).replace("__APPLY__",apply)
            cpp=cpp.replace("ADDRESS",typ).replace("ARCH",arch)
            cpp=cpp.replace("IMPL",impl).replace("PINNED_EXPECTED","true" if impl=="pinned" else "false")
            path=Path(folder)/(f"{arch}_{impl}.cpp")
            path.write_text(cpp)
            for opt in ("-O0","-O2"):
                exe=Path(folder)/(f"{arch}_{impl}{opt}")
                build=subprocess.run([compiler,"-std=c++20",opt,"-pthread","-Wall","-Wextra","-Werror",
                                      "-fsanitize=undefined","-fno-sanitize-recover=all",
                                      str(path),"-o",str(exe)],capture_output=True,text=True,timeout=55)
                assert build.returncode==0,(arch,impl,opt,build.stderr[-4300:])
                run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=25)
                assert run.returncode==0,(arch,impl,opt,run.stdout,run.stderr[-3000:])
                assert f"arch={arch} impl={impl}" in run.stdout
                print(run.stdout.strip(),opt,flush=True)
print("F02_PS5_JIT_COMPILATION_TIMING_NOT_PROVEN source_extracted_invalidation_only")


# J01: execute the native A32 source-extracted RAII cold timer in the
# F02 host gate. No PS5 SDK, game JIT work, or release-mode profiling.
a32=(ROOT/ARCHES["A32"][1]).read_text()
assert 'EDEN_JIT_A32_DEV_PROFILE=1' in HEADLESS
assert 'if(EDEN_DEV_PROFILE)\n        set_property(SOURCE' in HEADLESS
assert a32.index('if (auto block = emitter.GetBasicBlock(descriptor))') < a32.index('struct EdenCompileTimer {')
assert 'if (eden_jit_evacuation) eden_jit_evacuation(unsigned(conf.processor_id));' in a32
assert 'eden_jit_cache_event(unsigned(conf.processor_id),' in a32
assert 'eden_jit_phases(unsigned(conf.processor_id),' in a32
assert 'eden_compile_timer.active && eden_jit_phases' in a32
opener='        struct EdenCompileTimer {'
closer='        } eden_compile_timer{unsigned(conf.processor_id)};'
assert a32.count(opener)==a32.count(closer)==1
src=a32[a32.index(opener):a32.index(closer)+len(closer)]
model=r"""
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
inline bool detailed=false;
inline unsigned calls=0;
inline unsigned long long cpu_ns=0;
extern "C" bool eden_native_detailed_logging() noexcept {return detailed;}
extern "C" void eden_jit_compile(unsigned core,unsigned long long ns){
    assert(core==2);++calls;cpu_ns+=ns;
}
struct Config{unsigned processor_id{2};};
int main(){
    Config conf;
    auto compile=[&](bool hit){
        if(hit)return;
        __ACTUAL__
        std::atomic<unsigned> n{0};
        for(unsigned i=0;i<1500;++i)n.fetch_add(1,std::memory_order_relaxed);
        assert(n.load()==1500);
    };
    compile(true);assert(calls==0);
    compile(false);assert(calls==0);
    detailed=true;
    compile(true);assert(calls==0);
    compile(false);assert(calls==1&&cpu_ns>0);
    detailed=false;
    compile(false);assert(calls==1);
    std::puts("F07_A32_JIT_ACCOUNTING_PASS");
}
""".replace("__ACTUAL__",src)
with tempfile.TemporaryDirectory(prefix="f07-j01-a32-") as folder:
    source=Path(folder)/"a32.cpp"
    source.write_text(model)
    for opt in ("-O0","-O2"):
        output=Path(folder)/f"model-{opt[1:]}"
        build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                              "-fsanitize=undefined","-fno-sanitize-recover=all",
                              str(source),"-o",str(output)],capture_output=True,text=True,timeout=50)
        assert build.returncode==0,(opt,build.stderr[-3000:])
        run=subprocess.run([str(output)],capture_output=True,text=True,timeout=10)
        assert run.returncode==0,(opt,run.stderr[-3000:])
        assert "F07_A32_JIT_ACCOUNTING_PASS" in run.stdout
        print(f"F07_A32_JIT_ACCOUNTING_PASS {opt} source_extracted=1 quiet=1")

