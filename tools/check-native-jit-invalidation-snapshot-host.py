#!/usr/bin/env python3
"""Compile actual A32/A64 cache-invalidation entry and drain against reentrant requests.

The production method must release invalidation_mutex BEFORE emitter work.
A request arriving during the old drain must remain pending and must not be
silently cleared by the old operation. No title or console timing is inferred.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
owners = {
    "a32": root / "vendor/encore-active/eden-core/src/dynarmic/backend/x64/a32_interface_native.cpp",
    "a64": root / "vendor/encore-active/eden-core/src/dynarmic/backend/x64/a64_interface_standard.cpp",
}
shared = (root / "vendor/encore-active/eden-core/dynarmic/shared-jit/jit_impl.inc").read_text()
assert "ranges.swap(invalid_cache_ranges);" in shared

def method(src: str, name: str) -> str:
    marker = f"    void {name}("
    assert src.count(marker) == 1, name
    beg = src.index(marker)
    brace = src.index("{", beg)
    level = 0
    for i in range(brace, len(src)):
        if src[i] == "{":
            level += 1
        elif src[i] == "}":
            level -= 1
            if level == 0:
                return src[beg:i + 1]
    raise AssertionError("unterminated " + name)

for arch, path in owners.items():
    source = path.read_text()
    apply = method(source, "PerformRequestedCacheInvalidation")
    queue = method(source, "InvalidateCacheRange")
    clear = method(source, "ClearCache")
    assert apply.count("ranges.swap(invalid_cache_ranges);") == 1
    assert apply.index("ranges.swap(invalid_cache_ranges);") < apply.index("emitter.InvalidateCacheRanges(ranges)")
    assert apply.index("\n            }\n\n            if (!clear_all") < apply.index("jit_state.ResetRSB();")
    assert "invalid_cache_ranges.clear();" not in apply
    assert "invalidate_entire_cache = false;" in apply
    assert "HaltExecution(HaltReason::CacheInvalidation);" in queue
    assert "HaltExecution(HaltReason::CacheInvalidation);" in clear

    # Pressure and failed memory commitment must use the SAME lock-protected
    # full-clear entry point as guest invalidations. The former unguarded
    # writes of invalidate_entire_cache introduced a data race.
    pressure_pair = ("            ClearCache();\n"
                     "            PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);")
    get_block = source[source.index("if (block_of_code.SpaceRemaining() < MINIMUM_REMAINING_CODESIZE)"):]
    get_block = get_block[:get_block.index("        // JIT Compile") if "        // JIT Compile" in get_block else get_block.index("        // LocationDescriptor")]
    assert get_block.count(pressure_pair) == 2, arch
    assert "invalidate_entire_cache = true;" not in get_block, arch
    pressure_methods = (
        "    void PressureEvacuation() {\n" + pressure_pair + "\n    }\n"
        "    void CommitFailureEvacuation() {\n" + pressure_pair + "\n    }"
    )

    scalar = "u32" if arch == "a32" else "u64"
    fixture = r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>
using u32=std::uint32_t;
using u64=std::uint64_t;
using Address=ADDR;
enum class HaltReason { None, CacheInvalidation };
bool Has(HaltReason a, HaltReason b) { return a == b; }
namespace boost::icl {
template <typename T> struct discrete_interval {
    T lo{}, hi{};
    static discrete_interval closed(T lo,T hi){return {lo,hi};}
};
template <typename T> struct interval_set {
    std::vector<std::pair<T,T>> spans;
    void add(discrete_interval<T> x){spans.emplace_back(x.lo,x.hi);}
    bool empty() const {return spans.empty();}
    void swap(interval_set& other){spans.swap(other.spans);}
};
}
static bool detailed = true;
static unsigned reported[2]{};
// Match the weak host hooks declared by the actual maintained JIT unit.
// A non-weak fixture declaration makes Clang correctly complain that the
// source's optional function-pointer checks can never be false here.
extern "C" bool eden_native_detailed_logging() noexcept __attribute__((weak));
extern "C" void eden_jit_cache_event(unsigned,unsigned) __attribute__((weak));
extern "C" bool eden_native_detailed_logging() noexcept {return detailed;}
extern "C" void eden_jit_cache_event(unsigned core,unsigned kind){
    assert(core==2 && kind<2); ++reported[kind];
}
struct Code {
    unsigned cleared{};
    void ClearCache(){++cleared;}
};
struct State {
    unsigned resets{};
    void ResetRSB(){++resets;}
};
struct Emitter {
    unsigned ranged{}, cleared{};
    std::vector<std::pair<Address,Address>> last;
    std::function<void()> on_range, on_full;
    void InvalidateCacheRanges(const boost::icl::interval_set<Address>& r){
        ++ranged; last=r.spans;
        if(on_range)on_range();
    }
    void ClearCache(){++cleared; if(on_full)on_full();}
};
struct Conf {unsigned processor_id=2;};
// The test fixture rejects writes to shared full-clear state without the
// invalidation mutex. Old pressure code fails deterministically.
struct TrackedMutex {
    std::mutex inner;
    static thread_local unsigned depth;
    void lock() { inner.lock(); ++depth; }
    bool try_lock() { if (!inner.try_lock()) return false; ++depth; return true; }
    void unlock() { --depth; inner.unlock(); }
};
thread_local unsigned TrackedMutex::depth = 0;
struct TrackedFlag {
    bool state{};
    operator bool() const { return state; }
    TrackedFlag& operator=(bool next) {
        if (!TrackedMutex::depth) {
            std::fputs("UNSYNCHRONIZED_INVALIDATION_WRITE\n", stderr);
            std::abort();
        }
        state = next;
        return *this;
    }
};
struct Probe {
    TrackedMutex invalidation_mutex;
    TrackedFlag invalidate_entire_cache{};
    boost::icl::interval_set<Address> invalid_cache_ranges;
    unsigned halts=0, clear_halts=0;
    bool halted=false;
    State jit_state;
    Code block_of_code;
    Emitter emitter;
    Conf conf;
    void HaltExecution(HaltReason){++halts; halted=true;}
    void ClearHalt(HaltReason){++clear_halts; halted=false;}
METHOD_CLEAR
METHOD_QUEUE
METHOD_APPLY
PRESSURE_METHODS
    void UnsafePressureForNegativeControl() {
        invalidate_entire_cache = true;
        PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    }
};
int main(){
#ifdef NEGATIVE_UNSYNCHRONIZED_PRESSURE
    Probe broken;
    broken.UnsafePressureForNegativeControl();
    return 0;
#endif
    Probe p;
    assert(!p.halted);
    p.PerformRequestedCacheInvalidation(HaltReason::None);
    assert(p.clear_halts==0);

    // Real emitter gets a snapshot of the first request. Its reentrant guest
    // write must NOT wait on invalidation_mutex nor disappear afterward.
    p.emitter.on_range=[&](){
        bool unlocked=p.invalidation_mutex.try_lock();
        assert(unlocked);
        p.invalidation_mutex.unlock();
        if(p.emitter.ranged==1) p.InvalidateCacheRange(Address(0x200),4);
    };
    p.InvalidateCacheRange(Address(0x100),8);
    assert(p.halted && p.halts==1);
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.emitter.ranged==1 && p.emitter.last.size()==1);
    assert(p.emitter.last[0]==std::make_pair(Address(0x100),Address(0x107)));
    assert(p.halted && p.halts==2);
    assert(p.jit_state.resets==1 && p.clear_halts==1);
    assert(p.invalid_cache_ranges.spans.size()==1);
    assert(p.invalid_cache_ranges.spans[0]==std::make_pair(Address(0x200),Address(0x203)));

    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.emitter.ranged==2 && p.emitter.last.size()==1);
    assert(p.emitter.last[0]==std::make_pair(Address(0x200),Address(0x203)));
    assert(!p.halted && p.invalid_cache_ranges.empty());

    // A full clear is also processed outside the lock. New incremental writes
    // during that clear must be queued as the NEXT invalidation.
    p.emitter.on_full=[&](){
        bool unlocked=p.invalidation_mutex.try_lock();
        assert(unlocked);
        p.invalidation_mutex.unlock();
        p.InvalidateCacheRange(Address(0x300),4);
    };
    p.ClearCache();
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.block_of_code.cleared==1 && p.emitter.cleared==1);
    assert(p.halted && !p.invalidate_entire_cache);
    assert(p.invalid_cache_ranges.spans.size()==1);
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.emitter.ranged==3 && p.emitter.last[0]==std::make_pair(Address(0x300),Address(0x303)));
    assert(p.invalid_cache_ranges.empty() && !p.halted);
    assert(p.jit_state.resets==4);
#if defined(EDEN_JIT_A64_DEV_PROFILE)
    assert(reported[0]==1 && reported[1]==3);
#else
    assert(reported[0]==0 && reported[1]==0);
#endif
    // A redundant halt without a queued request is not an invalidation.
    auto old_resets=p.jit_state.resets;
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.jit_state.resets==old_resets);

    // Test the TWO actual GetBlock pressure/commit-retry handoff snippets.
    // A new guest invalidation raised during an emitter clear remains queued
    // for the next drain; repeated pressure requests complete without loss.
    detailed = false;
    Probe pressured;
    pressured.emitter.on_full = [&]() {
        bool unlocked = pressured.invalidation_mutex.try_lock();
        assert(unlocked);
        pressured.invalidation_mutex.unlock();
        if (pressured.emitter.cleared == 1) {
            // The real writer runs on another host thread while the JIT
            // invalidates its prior snapshot. Join would deadlock if the
            // JIT still owned invalidation_mutex across emitter.ClearCache.
            std::thread guest_writer([&] {
                pressured.InvalidateCacheRange(Address(0x400), 4);
            });
            guest_writer.join();
        }
    };
    pressured.InvalidateCacheRange(Address(0x300), 8);
    pressured.PressureEvacuation();
    assert(pressured.emitter.cleared == 1);
    assert(pressured.halted && pressured.invalid_cache_ranges.spans.size() == 1);
    assert(pressured.invalid_cache_ranges.spans[0] ==
           std::make_pair(Address(0x400), Address(0x403)));
    pressured.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(pressured.invalid_cache_ranges.empty() && !pressured.halted);
    pressured.CommitFailureEvacuation();
    assert(pressured.emitter.cleared == 2 && !pressured.halted);
    std::puts("NATIVE_JIT_INVALIDATION_SNAPSHOT_PASS");
}
""".replace("ADDR", scalar).replace("METHOD_CLEAR",clear).replace("METHOD_QUEUE",queue).replace("METHOD_APPLY",apply).replace("PRESSURE_METHODS",pressure_methods)
    compiler = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
    assert compiler, "C++20 compiler required"
    with tempfile.TemporaryDirectory(prefix="encore-jit-invalidation-") as temp:
        file = Path(temp) / "test.cpp"
        file.write_text(fixture)
        variants = ("release","dev") if arch == "a64" else ("release",)
        for variant in variants:
            for optimize in ("-O0", "-O2"):
                bin = Path(temp) / (arch + "-" + variant + optimize)
                flags = ["-DEDEN_JIT_A64_DEV_PROFILE=1"] if variant == "dev" else []
                subprocess.run([compiler,"-std=c++20",optimize,"-pthread",
                                "-Wall","-Wextra","-Werror","-fsanitize=undefined",
                                "-fno-sanitize-recover=all",*flags,str(file),"-o",str(bin)],
                               check=True,timeout=45)
                subprocess.run([str(bin)],check=True,timeout=12)
                print("JIT_SNAPSHOT_HOST_PASS",arch,variant,optimize)
                negative_bin = Path(temp) / (arch + "-" + variant + optimize + "-old-race")
                subprocess.run([compiler,"-std=c++20",optimize,"-pthread",
                                "-Wall","-Wextra","-Werror","-fsanitize=undefined",
                                "-fno-sanitize-recover=all",
                                "-DNEGATIVE_UNSYNCHRONIZED_PRESSURE=1",*flags,
                                str(file),"-o",str(negative_bin)],
                               check=True,timeout=45)
                old = subprocess.run([str(negative_bin)],capture_output=True,
                                     text=True,timeout=12)
                assert old.returncode != 0 and "UNSYNCHRONIZED_INVALIDATION_WRITE" in old.stderr
                print("JIT_PRESSURE_OLD_UNGUARDED_WRITE_REJECTED",arch,variant,optimize)
