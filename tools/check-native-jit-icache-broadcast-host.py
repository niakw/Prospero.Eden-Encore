#!/usr/bin/env python3
"""Source-extracted A64 cache-operation broadcast to all process core interfaces.

Host witness proves fan-out, line alignment, per-ISA full-flush handling,
and no loss of the JIT halt; does NOT certify PS5 core quiescence/FPS.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
A64=(ROOT/"vendor/encore-active/eden-core/src/core/arm/dynarmic/arm_dynarmic_64.cpp").read_text()
DEBUG=(ROOT/"vendor/sources/eden/src/core/arm/debug.cpp").read_text()
PATCH=(ROOT/"headless/backports/eden-dynarmic-icache-coherence.patch").read_text()
FLOW=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-native-jit-icache-broadcast-host.py" in FLOW
cb_begin="void DynarmicCallbacks64::InstructionCacheOperationRaised("
cb_end="\nvoid DynarmicCallbacks64::ExceptionRaised("
assert A64.count(cb_begin)==1 and A64.count(cb_end)==1
callback=A64[A64.index(cb_begin):A64.index(cb_end)].rstrip()
fn_begin="void InvalidateInstructionCacheRange(const Kernel::KProcess* process, u64 address, u64 size) {"
fn_end="\nstd::vector<BacktraceEntry> GetBacktraceFromContext("
assert DEBUG.count(fn_begin)==1 and DEBUG.count(fn_end)==1
broadcast=DEBUG[DEBUG.index(fn_begin):DEBUG.index(fn_end)].rstrip()
assert "Core::InvalidateInstructionCacheRange(m_process, cache_line_start, ICACHE_LINE_SIZE)" in callback
assert "InvalidateAllToPoUInnerSharable" in callback
assert "Core::Hardware::NUM_CPU_CORES" in broadcast
assert "m_parent.m_jit->HaltExecution" in callback
assert "Core::InvalidateInstructionCacheRange(m_process, cache_line_start, ICACHE_LINE_SIZE);" in PATCH
cxx=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
using u64=std::uint64_t;
namespace Dynarmic {
enum class HaltReason {CacheInvalidation};
namespace A64 {
enum class InstructionCacheOperation {
    InvalidateByVAToPoU,InvalidateAllToPoU,
    InvalidateAllToPoUInnerSharable,Unknown
};
}
}
#define LOG_DEBUG(...) ((void)0)
namespace Core {
namespace Hardware {constexpr std::size_t NUM_CPU_CORES=4;}
struct FakeInterface {
    unsigned calls=0;
    u64 last_address=0;
    u64 last_size=0;
    void InvalidateCacheRange(u64 addr,u64 size){
        ++calls;last_address=addr;last_size=size;
    }
};
struct FakeJit {
    unsigned halts=0;
    void HaltExecution(Dynarmic::HaltReason value){
        assert(value==Dynarmic::HaltReason::CacheInvalidation);
        ++halts;
    }
};
struct ArmDynarmic64 {
    FakeJit jit;
    FakeJit* m_jit=&jit;
    unsigned clear_count=0;
    void ClearInstructionCache(){++clear_count;}
};
}
namespace Kernel {
struct KProcess {
    std::array<Core::FakeInterface*,4> interfaces{};
    Core::FakeInterface* GetArmInterface(std::size_t i) const{
        return interfaces.at(i);
    }
};
}
namespace Core {
void InvalidateInstructionCacheRange(const Kernel::KProcess*,u64,u64);
struct DynarmicCallbacks64 {
    ArmDynarmic64& m_parent;
    Kernel::KProcess* m_process;
    u64 last_code_addr=0xfeed;
    void InstructionCacheOperationRaised(Dynarmic::A64::InstructionCacheOperation,u64);
};
INJECT_BROADCAST
INJECT_CALLBACK
}
int main(){
    Core::FakeInterface cpu0,cpu2,cpu3;
    Kernel::KProcess process{{&cpu0,nullptr,&cpu2,&cpu3}};
    Core::ArmDynarmic64 parent;
    Core::DynarmicCallbacks64 cb{parent,&process};
    using Op=Dynarmic::A64::InstructionCacheOperation;
    cb.InstructionCacheOperationRaised(Op::InvalidateByVAToPoU,0x1234);
    for(auto* p:{&cpu0,&cpu2,&cpu3}){
        assert(p->calls==1 && p->last_address==0x1200 && p->last_size==64);
    }
    assert(cb.last_code_addr==~u64{0} && parent.clear_count==0 && parent.jit.halts==1);
    cb.InstructionCacheOperationRaised(Op::InvalidateByVAToPoU,0x127f);
    for(auto* p:{&cpu0,&cpu2,&cpu3})assert(p->calls==2 && p->last_address==0x1240);
    cb.InstructionCacheOperationRaised(Op::InvalidateAllToPoU,0);
    cb.InstructionCacheOperationRaised(Op::InvalidateAllToPoUInnerSharable,0);
    for(auto* p:{&cpu0,&cpu2,&cpu3})assert(p->calls==2);
    assert(parent.clear_count==2 && parent.jit.halts==4);
    cb.InstructionCacheOperationRaised(Op::Unknown,0);
    assert(parent.clear_count==2 && parent.jit.halts==5);
    std::puts("EDEN_ICACHE_PROCESS_BROADCAST_HOST_PASS");
}
""".replace("INJECT_BROADCAST",broadcast).replace("INJECT_CALLBACK",callback)
compiler=shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="encore-icache-broadcast-") as tmp:
    src=Path(tmp)/"broadcast.cpp"
    exe=Path(tmp)/"broadcast"
    src.write_text(cxx)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(src),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("EDEN_ICACHE_BROADCAST_SOURCE_EXTRACTED; PS5 execution/fps unmeasured")
