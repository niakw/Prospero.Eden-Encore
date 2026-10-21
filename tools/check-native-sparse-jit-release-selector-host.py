#!/usr/bin/env python3
"""Compile actual Dynarmic sparse-commit method with and without DEV option."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-core/src/dynarmic/backend/x64/block_of_code_native.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
start="void BlockOfCode::EnsureMemoryCommitted([[maybe_unused]] size_t codesize) {"
end="\nHaltReason BlockOfCode::RunCode("
assert source.count(start)==source.count(end)==1
method=start+source.split(start,1)[1].split(end,1)[0].rstrip()
assert "#if defined(PS5_NATIVE) && defined(EDEN_SPARSE_JIT_DEV)" in method
assert "sparse_jit_cache.load(std::memory_order_relaxed)" in method
assert "if(EDEN_SPARSE_JIT_DEV)\n    target_compile_definitions(dynarmic PRIVATE EDEN_SPARSE_JIT_DEV=1)" in cmake
assert 'EDEN_SPARSE_JIT_DEV OR' in cmake or 'EDEN_SPARSE_JIT_DEV OR' in cmake
cc=shutil.which("clang++-18") or shutil.which("clang++")
assert cc
fixture=r"""
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <new>
using u8=std::uint8_t;
namespace Eden::Experimental {
inline std::atomic<bool> sparse_jit_cache{false};
}
inline unsigned planned=0,commits=0;
namespace Eden::Jit {
struct Plan {bool valid;std::size_t bytes;bool clamped;};
inline Plan PlanSparseCommit(std::size_t current,std::size_t add,std::size_t){
 ++planned;return {true,current+add,false};
}
}
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
__METHOD__
int main(){
 BlockOfCode b;
 b.EnsureMemoryCommitted(7);
 assert(planned==0 && commits==0);
 Eden::Experimental::sparse_jit_cache.store(true);
 b.EnsureMemoryCommitted(17);
#ifdef EDEN_SPARSE_JIT_DEV
 assert(planned==1 && commits==1);
#else
 assert(planned==0 && commits==0);
#endif
}
""".replace("__METHOD__",method)
with tempfile.TemporaryDirectory(prefix="eden-sparse-selector-") as tmp:
    d=Path(tmp);source_file=d/"selection.cpp"
    source_file.write_text(fixture)
    for name,flags in (("release",[]),("developer",["-DEDEN_SPARSE_JIT_DEV=1"])):
        executable=d/name
        subprocess.run([cc,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                        "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                        "-DPS5_NATIVE=1",*flags,str(source_file),"-o",str(executable)],
                       check=True,timeout=90)
        subprocess.run([str(executable)],check=True,timeout=30,capture_output=True)
        image=executable.read_bytes()
        marker=b"EDEN_JIT_SPARSE_COMMIT_FAILED"
        if name=="release":
            assert marker not in image, "sparse runtime unexpectedly linked into release"
        else:
            assert marker in image, "DEV source selection did not compile sparse path"
print("NATIVE_JIT_SPARSE_SELECTOR_HOST_PASS release_no_sparse_atomic=1 developer_opt_in=1 binary_marker=1")
