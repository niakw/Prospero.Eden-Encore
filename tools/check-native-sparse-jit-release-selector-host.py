#!/usr/bin/env python3
"""The only PS5 native release must compile the sparse JIT page commit."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
src=(root/"vendor/encore-active/eden-core/src/dynarmic/backend/x64/block_of_code_native.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
pkg=(root/"tools/build-package.sh").read_text()
app=(root/"headless/main.cpp").read_text()
start="void BlockOfCode::EnsureMemoryCommitted([[maybe_unused]] size_t codesize) {"
end="\nHaltReason BlockOfCode::RunCode("
assert src.count(start)==src.count(end)==1
method=start+src.split(start,1)[1].split(end,1)[0].rstrip()
assert "#ifdef PS5_NATIVE" in method
assert "defined(EDEN_SPARSE_JIT_DEV)" not in src
assert "EDEN_SPARSE_JIT_DEV" not in cmake
assert "EDEN_SPARSE_JIT_DEV" not in pkg
assert "\ndev)\n" not in pkg
assert "experimental_sparse_jit = true;" in app
assert "if (!Common::ProbeSparseJitAlias())" in app
assert 'throw std::runtime_error("PS5 sparse JIT alias preflight failed")' in app
cc=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert cc
code=r"""
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <new>
using u8=std::uint8_t;
namespace Eden::Jit {
struct Plan {bool valid;std::size_t bytes;bool clamped;};
inline Plan PlanSparseCommit(std::size_t current,std::size_t add,std::size_t){
 return {true,current+add,false};
}
}
inline unsigned commits=0;
namespace Common {
inline bool CommitSparseJitCode(u8*,std::size_t){++commits;return true;}
}
struct BlockOfCode {
 std::size_t size_=10,maxSize_=256;
 u8 bytes[256]{};
 std::size_t getSize()const{return size_;}
 const u8* getCode()const{return bytes;}
 void EnsureMemoryCommitted(std::size_t);
};
""" + method + r"""
int main(){
 BlockOfCode b;
 b.EnsureMemoryCommitted(7);
#ifdef PS5_NATIVE
 assert(commits==1);
#else
 assert(commits==0);
#endif
}
"""
with tempfile.TemporaryDirectory(prefix="eden-sparse-native-only-") as temp:
    p=Path(temp)/"jit.cpp"
    p.write_text(code)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            exe=Path(temp)/(("native" if native else "host")+opt[1:])
            flags=["-DPS5_NATIVE=1"] if native else []
            subprocess.run([cc,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                            *flags,str(p),"-o",str(exe)],check=True,
                           capture_output=True,text=True,timeout=40)
            subprocess.run([str(exe)],check=True,timeout=20)
print("NATIVE_SINGLE_SPARSE_JIT_RELEASE_PASS native=1 host=1 O0=1 O2=1 no_dev_selector=1")
