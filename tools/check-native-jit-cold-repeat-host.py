#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""F02: execute real pinned/Encore JIT lookup + invalidation C++ bodies.

A32 and default A64: cold blocks, repeated hits, partial invalidation,
recompilation, and full cache reset. Translators, code emitters and their
synthetic CPU cost are mocked; native JIT entry/exit, cache operations and
selection are from checked-in C++ source. Not a PS5 compilation/FPS benchmark.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
CMAKE=(ROOT/"headless/CMakeLists.txt").read_text()
FAST=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
FULL=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
CMD="python3 -B tools/check-native-jit-cold-repeat-host.py"
assert CMD in FAST and CMD in FULL
assert "a32_interface_native.cpp" in CMAKE
assert "a64_interface_standard.cpp" in CMAKE
assert 'option(EDEN_JIT_COMPILE_BATCH "Compile bounded A64 successor chains on a cache miss" OFF)' in CMAKE

ARCH={
 "A32":("vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/a32_interface.cpp",
        "vendor/encore-active/eden-core/src/dynarmic/backend/x64/a32_interface_native.cpp"),
 "A64":("vendor/sources/eden/src/dynarmic/src/dynarmic/backend/x64/a64_interface.cpp",
        "vendor/encore-active/eden-core/src/dynarmic/backend/x64/a64_interface_standard.cpp"),
}
def extract(source,begin):
    assert source.count(begin)==1,begin
    a=source.index(begin)
    open_brace=source.index("{",a)
    depth=0
    for i in range(open_brace,len(source)):
        if source[i]=="{":depth+=1
        elif source[i]=="}":
            depth-=1
            if depth==0:return source[a:i+1]
    raise AssertionError(begin)

TEMPLATE=r"""
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <new>
#include <optional>
#include <utility>
#include <vector>
using u32=std::uint32_t;
using u64=std::uint64_t;
using CodePtr=void*;
using Clock=std::chrono::steady_clock;
extern "C" void eden_jit_block(unsigned,unsigned long long,const void*,unsigned long long)
    __attribute__((weak));
extern "C" bool eden_native_detailed_logging() noexcept __attribute__((weak));
extern "C" void eden_jit_evacuation(unsigned) __attribute__((weak));
enum class HaltReason {None,CacheInvalidation};
bool Has(HaltReason a,HaltReason b){return a==b;}
namespace boost::icl {
template<class T> struct discrete_interval {
    T lo{},hi{};
    static discrete_interval closed(T a,T b){return {a,b};}
};
template<class T> struct interval_set {
    std::vector<discrete_interval<T>> spans;
    void add(discrete_interval<T> s){spans.push_back(s);}
    bool empty()const{return spans.empty();}
    void clear(){spans.clear();}
    void swap(interval_set& s){spans.swap(s.spans);}
};
}
namespace IR {
struct LocationDescriptor {
    u64 value{};
    explicit LocationDescriptor(u64 n=0):value(n){}
    u64 Value()const{return value;}
    bool operator<(const LocationDescriptor& rhs)const{return value<rhs.value;}
};
struct Block {
    u64 key{};
    template<class Loc> void Reset(Loc d){key=d.Value();}
};
}
namespace A32 {
struct LocationDescriptor:IR::LocationDescriptor {
    using IR::LocationDescriptor::LocationDescriptor;
    LocationDescriptor(IR::LocationDescriptor loc):IR::LocationDescriptor(loc){}
};
struct TranslateFlags {int arch_version{};bool unpredictable{},hints{};};
template<class Callback>
void Translate(IR::Block& block, LocationDescriptor d,Callback*,TranslateFlags){
    assert(block.key==d.Value());
}
}
namespace A64 {
struct LocationDescriptor:IR::LocationDescriptor {
    using IR::LocationDescriptor::LocationDescriptor;
    LocationDescriptor(IR::LocationDescriptor loc):IR::LocationDescriptor(loc){}
};
struct TranslateFlags {bool unpredictable{},wall_clock{};};
template<class GetCode>
void Translate(IR::Block& block, LocationDescriptor d,GetCode code,TranslateFlags){
    assert(block.key==d.Value());
    assert(code(d.Value())!=0);
}
}
struct Callbacks {u32 MemoryReadCode(u64 addr){return static_cast<u32>(addr|1u);}};
struct Conf {
    Callbacks* callbacks{};
    u32 processor_id{3},code_cache_size{32*1024*1024};
    int arch_version{8};
    bool define_unpredictable_behaviour{},hook_hint_instructions{},wall_clock_cntpct{};
};
namespace Optimization {
void Optimize(IR::Block& block,const Conf&,int){
    assert(block.key!=0);
}
}
struct BlockDescriptor {CodePtr entrypoint{};size_t size{};};
struct A32EmitX64 {using BlockDescriptor=::BlockDescriptor;};
struct CodeSpace {
    size_t capacity{64*1024*1024};
    unsigned commits{},clears{};
    size_t SpaceRemaining()const{return capacity;}
    void EnsureMemoryCommitted(size_t n){assert(n<=capacity);++commits;}
    void ClearCache(){++clears;}
};
struct Emitter {
    std::map<u64,BlockDescriptor> blocks;
    unsigned emits{},lookups{},invalidations{},clears{};
    std::atomic<u64> work{0};
    std::optional<BlockDescriptor> GetBasicBlock(IR::LocationDescriptor d){
        ++lookups;
        const auto it=blocks.find(d.Value());
        if(it==blocks.end())return std::nullopt;
        return it->second;
    }
    BlockDescriptor Emit(const IR::Block& ir){
        ++emits;
        u64 v=ir.key;
        for(unsigned i=0;i<2048;++i)
            v=(v*1664525ULL+1013904223ULL)^(v>>7);
        work.fetch_add(v,std::memory_order_relaxed);
        BlockDescriptor block{reinterpret_cast<CodePtr>((ir.key|1ULL)<<4),32};
        assert(blocks.emplace(ir.key,block).second);
        return block;
    }
    void InvalidateCacheRanges(const boost::icl::interval_set<ADDR>& intervals){
        ++invalidations;
        for(auto it=blocks.begin();it!=blocks.end();){
            bool remove=false;
            for(const auto& range:intervals.spans)
                if(it->first>=range.lo && it->first<=range.hi)remove=true;
            if(remove)it=blocks.erase(it);
            else ++it;
        }
    }
    void ClearCache(){++clears;blocks.clear();}
};
struct JitState{unsigned resets{};void ResetRSB(){++resets;}};
struct Probe {
    Callbacks callbacks;
    Conf conf;
    IR::Block ir_block;
    CodeSpace block_of_code;
    Emitter emitter;
    int polyfill_options{};
    JitState jit_state;
    bool invalidate_entire_cache{};
    boost::icl::interval_set<ADDR> invalid_cache_ranges;
    std::mutex invalidation_mutex;
    unsigned halts{},cleared_halts{};
    Probe(){conf.callbacks=&callbacks;}
    void HaltExecution(HaltReason){++halts;}
    void ClearHalt(HaltReason){++cleared_halts;}
    void ClearCache();
    void InvalidateCacheRange(ADDR,size_t);
    void PerformRequestedCacheInvalidation(HaltReason);
    BLOCK_RET BLOCK_METHOD(IR::LocationDescriptor);
};
__NATIVE__
static CodePtr Lookup(Probe& p,u64 location){
    IR::LocationDescriptor d{location};
#if defined(SCENARIO_A32)
    return p.GetBasicBlock(d).entrypoint;
#else
    return p.GetBlock(d);
#endif
}
int main(){
    Probe p;
    constexpr unsigned blocks=32,repeat=16;
    std::array<CodePtr,blocks> entries{};
    auto run_pass=[&](unsigned* new_emits){
        const auto before=p.emitter.emits;
        for(unsigned k=0;k<blocks;++k){
            CodePtr result=Lookup(p,0x1000+8*k);
            assert(result);
            if(!entries[k])entries[k]=result;
            else assert(result==entries[k]);
        }
        *new_emits=p.emitter.emits-before;
    };
    unsigned cold{},hot{},recompile{},cleared{};
    const auto start=Clock::now();
    run_pass(&cold);
    const auto after_cold=Clock::now();
    for(unsigned n=0;n<repeat;++n)run_pass(&hot);
    const auto after_hot=Clock::now();
    // Exactly eight blocks from the middle of the populated cache.
    p.InvalidateCacheRange(static_cast<ADDR>(0x1000+12*8),8*8);
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.emitter.blocks.size()==24);
    run_pass(&recompile);
    assert(recompile==8);
    // A no-op drain must not force additional compilation or reset the RSB.
    const auto previous=p.jit_state.resets;
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.jit_state.resets==previous);
    p.ClearCache();
    p.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(p.emitter.blocks.empty());
    run_pass(&cleared);
    assert(cold==32 && hot==0 && cleared==32);
    assert(p.emitter.emits==72 && p.emitter.blocks.size()==32);
    assert(p.emitter.work.load(std::memory_order_relaxed)!=0);
    const auto cold_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(
        after_cold-start).count();
    const auto hot_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(
        after_hot-after_cold).count();
    assert(cold_ns>0 && hot_ns>0);
    // Default JIT profile maintains independent per-core code namespaces.
    // A range write in one core must never evict another core's block.
    Probe core0,core1;
    const CodePtr one=Lookup(core0,0x5000);
    const CodePtr two=Lookup(core1,0x5000);
    assert(one==two && core0.emitter.emits==1 && core1.emitter.emits==1);
    core0.InvalidateCacheRange(static_cast<ADDR>(0x5000),4);
    core0.PerformRequestedCacheInvalidation(HaltReason::CacheInvalidation);
    assert(core0.emitter.blocks.empty() && core1.emitter.blocks.size()==1);
    assert(Lookup(core0,0x5000)==one);
    assert(Lookup(core1,0x5000)==two);
    assert(core0.emitter.emits==2 && core1.emitter.emits==1);
    std::printf("F02_JIT_NATIVE_COLD_REPLAY_PASS arch=ARCH impl=IMPL "
                "cold=32 repeated_hits=512 recompile=8 full_clear_compile=32 "
                "total_emissions=72 isolated_cores=2 cold_total_ns=%lld hot_total_ns=%lld "
                "scope=source_extracted_synthetic_translator\n",
                static_cast<long long>(cold_ns),
                static_cast<long long>(hot_ns));
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="encore-f02-cold-") as folder:
    for arch,(baseline,maintained) in ARCH.items():
        for kind,path in (("pinned",baseline),("maintained",maintained)):
            source=(ROOT/path).read_text()
            name="GetBasicBlock" if arch=="A32" else "GetBlock"
            signature="    A32EmitX64::BlockDescriptor GetBasicBlock(" if arch=="A32" else "    CodePtr GetBlock("
            body=extract(source,signature)
            range_source=extract(source,"    void InvalidateCacheRange(")
            drain=extract(source,"    void PerformRequestedCacheInvalidation(")
            clear=extract(source,"    void ClearCache(")
            methods="\n".join((
                body.replace(signature,("A32EmitX64::BlockDescriptor " if arch=="A32" else "CodePtr ")+
                             "Probe::"+name+"(",1),
                range_source.replace("    void InvalidateCacheRange(","void Probe::InvalidateCacheRange(",1),
                drain.replace("    void PerformRequestedCacheInvalidation(","void Probe::PerformRequestedCacheInvalidation(",1),
                clear.replace("    void ClearCache(","void Probe::ClearCache(",1)))
            cpp=TEMPLATE.replace("ADDR","u32" if arch=="A32" else "u64")
            cpp=cpp.replace("BLOCK_RET","A32EmitX64::BlockDescriptor" if arch=="A32" else "CodePtr")
            cpp=cpp.replace("BLOCK_METHOD",name)
            cpp=cpp.replace("__NATIVE__",methods).replace("ARCH",arch).replace("IMPL",kind)
            file=Path(folder)/(f"{arch}_{kind}.cpp")
            file.write_text(cpp)
            for opt in ("-O0","-O2"):
                exe=Path(folder)/(f"{arch}_{kind}_{opt[1:]}")
                cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                     "-pthread","-fsanitize=undefined","-fno-sanitize-recover=all"]
                if arch=="A32":cmd+=["-DSCENARIO_A32=1"]
                if kind=="maintained":cmd+=["-DPS5_NATIVE=1"]
                cmd +=[str(file),"-o",str(exe)]
                build=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
                assert build.returncode==0,(arch,kind,opt,build.stderr[-4700:])
                run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=25)
                assert run.returncode==0,(arch,kind,opt,run.stdout,run.stderr[-4200:])
                assert f"arch={arch} impl={kind}" in run.stdout
                print(run.stdout.strip(),opt,flush=True)
print("F02_REAL_JIT_COMPILE_TIMING_NOT_PROVEN synthetic_emit_not_guest_translation")
