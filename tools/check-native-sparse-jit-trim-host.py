#!/usr/bin/env python3
"""Dev sparse JIT: exercise exact quiesced physical-tail trim and reuse policy.

The native source's guard/unmap/free ordering is compiled under a syscall
fixture, not rewritten as a Python approximation. Shipping sparse stays OFF.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
policy=root/"headless/jit-sparse-commit.h"
native=(root/"src/memory_pages.cpp").read_text()
jit=(root/"vendor/encore-active/eden-core/src/dynarmic/backend/x64/block_of_code_native.cpp").read_text()
allocator=(root/"headless/jit-allocator.h").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
assert "bool TrimSparseJitCode(void*, std::size_t live_code_end) noexcept;" in allocator
assert "target_include_directories(common PRIVATE \"\u0024{EDEN_PORT_DIR}\")" in cmake
assert "defined(EDEN_SPARSE_JIT_DEV)" in jit
assert "setSize(begin);" in jit
assert jit.index("setSize(begin);") < jit.index("::Common::TrimSparseJitCode(getCode(), begin)")
assert "sparse_jit_generation.fetch_add(1, std::memory_order_acq_rel);" in native
start="bool TrimSparseJitCode(void* executable, std::size_t live_code_end) noexcept {"
end="\n\n// The virtual reservation and every remaining physical chunk have one owner."
assert native.count(start)==1 and native.count(end)==1
method=start+native.split(start,1)[1].split(end,1)[0]
assert method.index("guard(rx);") < method.index("sceKernelReleaseDirectMemory(")
assert method.index("guard(rw);") < method.index("sceKernelReleaseDirectMemory(")
assert method.index("sparse_jit_generation.fetch_add(") < method.index("guard(rx);")
assert method.count("sparse_jit_committed_live.fetch_sub(")==1

cpp=r"""
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <unordered_map>
#include <vector>
#include <sys/mman.h>
#include "jit-sparse-commit.h"
namespace Common {
constexpr std::size_t LargePage=2u<<20;
struct SparseJitRegion {
    void* writable{};
    std::size_t capacity{},committed{};
    std::vector<std::int64_t> physical;
};
std::mutex sparse_jit_mutex;
std::unordered_map<void*,SparseJitRegion> sparse_jit_regions;
std::size_t sparse_jit_committed=0;
std::atomic<std::size_t> sparse_jit_committed_live{0};
std::atomic<std::uint64_t> sparse_jit_generation{1};
std::size_t guarded{},released{};
int sceKernelReleaseDirectMemory(std::int64_t, std::size_t length) {
    assert(length==LargePage);
    assert(guarded==(released+1)*2); // BOTH aliases guarded before physical free
    ++released;
    return 0;
}
void* FakeGuard(void* addr,std::size_t length,int prot,int flags,int fd,long off) {
    assert(addr && length==LargePage && prot==PROT_NONE);
    assert(flags & MAP_FIXED);
    assert(fd==-1 && off==0);
    ++guarded;
    return addr;
}
#define mmap FakeGuard
""" + method + r"""
#undef mmap
} // namespace Common
int main() {
    using namespace Common;
    constexpr std::size_t capacity=256u<<20;
    const auto rx=::mmap(nullptr,capacity,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    const auto rw=::mmap(nullptr,capacity,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(rx!=MAP_FAILED && rw!=MAP_FAILED);
    auto& state=sparse_jit_regions[rx];
    state.writable=rw;
    state.capacity=capacity;
    state.committed=128u<<20;
    for(std::size_t i=0;i<state.committed/LargePage;++i)
        state.physical.push_back(static_cast<std::int64_t>(i));
    sparse_jit_committed=state.committed;
    sparse_jit_committed_live.store(state.committed);
    const auto generation=sparse_jit_generation.load();
    assert(TrimSparseJitCode(rx,3u<<20));
    assert(state.committed==(6u<<20));
    assert(sparse_jit_committed==(6u<<20));
    assert(sparse_jit_committed_live.load()==(6u<<20));
    assert(released==61 && guarded==122);
    assert(sparse_jit_generation.load()>generation);
    // A stale positive fastpath from before clearing must no longer qualify.
    const auto old_generation=generation;
    assert(old_generation!=sparse_jit_generation.load());
    const auto next=Eden::Jit::PlanSparseCommit(state.committed,LargePage,capacity);
    assert(next.valid && next.bytes==(8u<<20));
    const auto no_more=Eden::Jit::PlanSparseTrim(3u<<20,state.committed,capacity,LargePage);
    assert(no_more.valid && no_more.release==0);
    assert(TrimSparseJitCode(rx,3u<<20));
    assert(released==61);
    assert(!TrimSparseJitCode(rx,7u<<20));
    assert(released==61);
    // The final 16-MiB arena must never decommit past a live 15-MiB prelude.
    const auto tiny=Eden::Jit::PlanSparseTrim(15u<<20,16u<<20,16u<<20,LargePage);
    assert(tiny.valid && tiny.release==0);
    assert(::munmap(rx,capacity)==0 && ::munmap(rw,capacity)==0);
}
"""
compiler=shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler missing"
with tempfile.TemporaryDirectory(prefix="eden-native-sparse-trim-") as d:
    file=Path(d)/"trim.cpp"
    file.write_text(cpp)
    for opt in ("-O0","-O2"):
        exe=Path(d)/("trim"+opt[1:])
        result=subprocess.run([compiler,"-std=c++20","-pthread",opt,"-Wall","-Wextra","-Werror",
                               "-I",str(root/"headless"),str(file),"-o",str(exe)],
                              capture_output=True,text=True,timeout=40)
        if result.returncode: raise AssertionError(result.stderr)
        subprocess.run([str(exe)],check=True,timeout=20)
print("PS5_SPARSE_JIT_TRIM_HOST_PASS guarded_aliases=1 physical_return=1 generation=1 recommit=1 O0=1 O2=1")
