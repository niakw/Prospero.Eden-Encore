#!/usr/bin/env python3
"""Exercise source-extracted native Dynarmic code-cache bounds under ASan/UBSan."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
active=(root/"vendor/encore-active/eden-core/src/dynarmic/backend/x64/block_of_code_native.cpp").read_text()
start="void* BlockOfCode::AllocateFromCodeSpace(size_t alloc_size) {"
assert active.count(start)==1
method=start+active.split(start,1)[1].split("\n}\n",1)[0]+"\n}"
assert "size_ >= maxSize_ || alloc_size >= maxSize_ - size_" in method
assert "size_ + alloc_size >= maxSize_" not in method
assert "EnsureMemoryCommitted(alloc_size);" in method
assert "memset(writableAddress(ret), 0, alloc_size);" in method
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler
program=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
namespace Xbyak {enum Error{ERR_CODE_IS_TOO_BIG};}
#define XBYAK_THROW(code) throw std::length_error("code space limit")
struct BlockOfCode {
 std::size_t size_=0,maxSize_=64;
 std::array<unsigned char,256> bytes{};
 unsigned commits=0;
 template<class T> T getCurr(){return reinterpret_cast<T>(bytes.data()+size_);}
 void EnsureMemoryCommitted(std::size_t){++commits;}
 void* writableAddress(void* addr){return addr;}
 void* AllocateFromCodeSpace(std::size_t alloc_size);
};
__METHOD__
static bool rejected(BlockOfCode& code,std::size_t n){
 try{code.AllocateFromCodeSpace(n);return false;}
 catch(const std::length_error&){return true;}
}
int main(){
 BlockOfCode code;
 code.bytes.fill(0x77);
 assert(code.AllocateFromCodeSpace(16)==code.bytes.data());
 assert(code.size_==16 && code.commits==1);
 for(unsigned i=0;i<16;++i)assert(code.bytes[i]==0);
 code.size_=32;
 assert(code.AllocateFromCodeSpace(31)==code.bytes.data()+32);
 assert(code.size_==63);
 assert(rejected(code,1));
 assert(rejected(code,64));
 assert(code.commits==2);
 code.size_=64;assert(rejected(code,0));
 code.size_=70;assert(rejected(code,0));
 code.size_=std::numeric_limits<std::size_t>::max()-8;
 code.maxSize_=std::numeric_limits<std::size_t>::max();
 assert(rejected(code,64));
 assert(rejected(code,std::numeric_limits<std::size_t>::max()));
 assert(code.commits==2);
}
""".replace("__METHOD__",method)
with tempfile.TemporaryDirectory(prefix="eden-jit-code-capacity-") as temp:
 d=Path(temp);code=d/"bounds.cpp";exe=d/"bounds"
 code.write_text(program)
 subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                 "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                 str(code),"-o",str(exe)],check=True,timeout=90)
 subprocess.run([str(exe)],check=True,timeout=30,capture_output=True)
print("NATIVE_JIT_CODE_SPACE_BOUNDS_PASS wrap_guard=1 exact_capacity=1 data_zeroing=1 sanitizer=1")
