#!/usr/bin/env python3
"""Compile the selected native GuestMemory header and check stale spans on empty reads."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
active=(root/"vendor/encore-active/eden-core/overrides/core/guest_memory.h").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
assert active.count("m_data_span = {};")==1
assert active.count("m_span_valid = false;")==1
assert "if (m_size == 0) {" in active
assert active.index("if (m_size == 0) {")<active.index("m_data_span = {};")<active.index("m_is_data_copy = true;")
assert 'target_include_directories(core BEFORE PUBLIC "${EDEN_NATIVE_DIRTY_HEADER_ROOT}")' in cmake
assert 'target_include_directories(video_core BEFORE PRIVATE "${EDEN_NATIVE_DIRTY_HEADER_ROOT}")' in cmake
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler
fixture=r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>
#include <vector>
using u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;
#include "core/guest_memory.h"
struct Memory {
 static constexpr bool HAS_FLUSH_INVALIDATION=true;
 std::array<u8,128> bytes{};
 bool contiguous=true;
 unsigned flushes=0,reads=0,writes=0,invalidations=0;
 Memory() {for(unsigned i=0;i<bytes.size();++i)bytes[i]=u8(i);}
 u8* GetSpan(u64 a,std::size_t count) {
    if(!contiguous || a>bytes.size() || count>bytes.size()-a) return nullptr;
    return bytes.data()+a;
 }
 void FlushRegion(u64,std::size_t){++flushes;}
 void InvalidateRegion(u64,std::size_t){++invalidations;}
 void ReadBlock(u64 a,void* dest,std::size_t n) {
    ++reads;assert(a<=bytes.size()&&n<=bytes.size()-a);
    std::memcpy(dest,bytes.data()+a,n);
 }
 void ReadBlockUnsafe(u64 a,void* dest,std::size_t n){ReadBlock(a,dest,n);}
 void WriteBlock(u64 a,const void* source,std::size_t n) {
    ++writes;assert(a<=bytes.size()&&n<=bytes.size()-a);
    std::memcpy(bytes.data()+a,source,n);
 }
 void WriteBlockUnsafe(u64 a,const void* source,std::size_t n){WriteBlock(a,source,n);}
 void WriteBlockCached(u64 a,const void* source,std::size_t n){WriteBlock(a,source,n);}
};
int main(){
 using namespace Core::Memory;
 Memory direct;
 GuestMemory<Memory,u8,GuestMemoryFlags::SafeRead> d(direct,4,8);
 assert(d.data()==direct.bytes.data()+4 && d.size()==8);
 assert(d.Read(50,0).empty());
 assert(d.data()==nullptr && d.size_bytes()==0);
 assert(d.Read(12,3).data()==direct.bytes.data()+12);
 assert(d.size()==3 && d[0]==12);
 Memory copy;copy.contiguous=false;
 GuestMemory<Memory,u8,GuestMemoryFlags::SafeRead> c(copy,7,5);
 assert(c.data()!=nullptr && c[0]==7 && copy.reads==1);
 assert(c.Read(80,0).empty());
 assert(c.data()==nullptr && c.size()==0 && copy.reads==1);
 assert(c.Read(9,2).size()==2 && c[0]==9 && copy.reads==2);
 Memory scoped;
 {
    GuestMemoryScoped<Memory,u8,GuestMemoryFlags::SafeReadWrite> dscoped(scoped,8,5);
    dscoped.Read(30,0);
    assert(dscoped.data()==nullptr && dscoped.size()==0);
 }
 assert(scoped.invalidations==0 && scoped.writes==0);
}
"""
with tempfile.TemporaryDirectory(prefix="eden-empty-guest-span-") as tmp:
    d=Path(tmp)
    (d/"common").mkdir()
    (d/"core").mkdir()
    (d/"core/guest_memory.h").write_text(active)
    (d/"common/assert.h").write_text("#pragma once\n#include <cassert>\n#define ASSERT(x) assert(x)\n")
    (d/"common/scratch_buffer.h").write_text(
      "#pragma once\n#include <vector>\n#include <span>\n"
      "namespace Common {template<class T> struct ScratchBuffer {"
      "std::vector<T> buf;void resize_destructive(std::size_t n){buf.resize(n);}"
      "operator std::span<T>() {return std::span<T>(buf);}};}\n")
    source=d/"fixture.cpp";exe=d/"fixture"
    source.write_text(fixture)
    subprocess.run([compiler,"-std=c++20","-O1","-g","-Wall","-Wextra","-Werror",
                    "-fsanitize=address,undefined","-fno-sanitize-recover=all",
                    "-I",str(d),str(source),"-o",str(exe)],check=True,timeout=90)
    subprocess.run([str(exe)],check=True,timeout=30,capture_output=True)
print("NATIVE_GUEST_EMPTY_READ_HOST_PASS cleared_direct=1 cleared_copy=1 reused=1 scoped_no_writeback=1")
