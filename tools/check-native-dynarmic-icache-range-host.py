#!/usr/bin/env python3
"""Compile maintained native A32/A64 cache-range methods with ASan/UBSan."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
A32=(ROOT/"vendor/encore-active/eden-core/src/core/arm/dynarmic/arm_dynarmic_32.cpp").read_text()
A64=(ROOT/"vendor/encore-active/eden-core/src/core/arm/dynarmic/arm_dynarmic_64.cpp").read_text()
PATCH=(ROOT/"headless/backports/eden-dynarmic-icache-coherence.patch").read_text()
FLOW=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
assert "python3 -B tools/check-native-dynarmic-icache-range-host.py" in FLOW
assert "static_cast<u64>(~u32{0})" in PATCH
assert PATCH.count("+    if (size == 0) {")==2
assert "@@ -432,6 +432,15 @@" in PATCH and "@@ -458,6 +459,10 @@" in PATCH

def method(text,name):
    anchor=f"void {name}::InvalidateCacheRange(u64 addr, std::size_t size) {{"
    assert text.count(anchor)==1
    return text[text.index(anchor):].split("\n}\n",1)[0]+"\n}"
a32=method(A32,"ArmDynarmic32")
a64=method(A64,"ArmDynarmic64")
cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
using u32=std::uint32_t;
using u64=std::uint64_t;
struct Callback{u64 last_code_addr=0x1234;};
struct Jit{
    unsigned clear=0, invalidated=0;
    u64 last_addr=0;
    std::size_t last_size=0;
    void ClearCache(){++clear;}
    void InvalidateCacheRange(u64 addr,std::size_t size){
        ++invalidated;last_addr=addr;last_size=size;
    }
};
struct ArmDynarmic32{
    Callback cb;Jit jit;Callback* m_cb=&cb;Jit* m_jit=&jit;
    void InvalidateCacheRange(u64,std::size_t);
};
struct ArmDynarmic64{
    Callback cb;Jit jit;Callback* m_cb=&cb;Jit* m_jit=&jit;
    void InvalidateCacheRange(u64,std::size_t);
};
INJECT32
INJECT64
int main(){
    ArmDynarmic32 x; ArmDynarmic64 y;
    x.InvalidateCacheRange(0x1000,0);y.InvalidateCacheRange(0x1000,0);
    assert(x.cb.last_code_addr==0x1234 && y.cb.last_code_addr==0x1234);
    assert(x.jit.invalidated==0 && y.jit.invalidated==0);
    x.InvalidateCacheRange(0x12345678,4);
    assert(x.jit.invalidated==1 && x.jit.last_addr==0x12345678 && x.cb.last_code_addr==~u64{0});
    x.InvalidateCacheRange(0x100000000ULL,4);
    assert(x.jit.clear==1 && x.jit.invalidated==1);
    x.InvalidateCacheRange(0xFFFFFFFFULL,4);
    assert(x.jit.invalidated==2 && x.jit.last_addr==0xFFFFFFFFULL);
    y.InvalidateCacheRange(0x100000000ULL,4);
    assert(y.jit.invalidated==1 && y.jit.last_addr==0x100000000ULL);
    assert(y.jit.clear==0 && y.cb.last_code_addr==~u64{0});
    std::puts("ENCORE_ICACHE_RANGE_A32_A64_PASS");
}
""".replace("INJECT32",a32).replace("INJECT64",a64)
compiler=shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="eden-jit-icache-range-") as name:
    root=Path(name);src=root/"test.cpp";exe=root/"test";src.write_text(cpp)
    subprocess.run([compiler,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    str(src),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30)
print("ENCORE_ICACHE_RANGE_HOST_ONLY; console frame times unmeasured")
