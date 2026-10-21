#!/usr/bin/env python3
"""Compile actual heap-commit function with/without DEV heap-growth logging."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/"src/memory_pages.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
start="bool CommitMemoryRange(void* address, std::size_t size, std::int64_t* physical_out) noexcept {"
end="bool CommitMemoryRange(void* address, std::size_t size) noexcept {"
assert source.count(start)==1 and source.count(end)==1
body=source[source.index(start):source.index(end)]
assert body.count("#ifdef EDEN_HEAP_GROWTH_TRACE")==4
assert body.count("#endif")==5  # four trace blocks and the PS5_NATIVE split
assert "std::memset(address, 0, size);" in body
assert "if (physical_out) *physical_out = physical;" in body
assert 'target_compile_definitions(common PRIVATE EDEN_HEAP_GROWTH_TRACE=1)' in cmake
assert 'if(EDEN_DEV_PROFILE)' in cmake
assert "EDEN_HEAP_GROWTH_TRACE" not in cmake.split('if(EDEN_DEV_PROFILE)',1)[0]
compiler=shutil.which("clang++-18") or shutil.which("clang++")
assert compiler, "clang++ required"
fixture=r"""
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <sys/mman.h>
namespace Common {
constexpr std::size_t LargePage=2u*1024u*1024u;
int timestamp_calls=0;
int logs=0;
int AllocateDirectOwned(std::size_t bytes, std::size_t align, std::int64_t* physical){
    assert(bytes==LargePage && align==LargePage);
    *physical=1337; return 0;
}
int sceKernelMapDirectMemory(void** at, std::size_t bytes, int perm, int flags,
                             std::int64_t phys, std::size_t align) {
    assert(*at!=nullptr && bytes==LargePage && phys==1337 && align==LargePage);
    assert(perm==(PROT_READ|PROT_WRITE) && flags==MAP_FIXED);
    return 0;
}
int sceKernelReleaseDirectMemory(std::int64_t, std::size_t) {abort();}
bool cpu_mapping_range(const void*, std::size_t) {return true;}
void Note(const char*) {++logs;}
#define clock_gettime(clock, address) (++timestamp_calls, (void)(clock), (void)(address), 0)
__BODY__
#undef clock_gettime
}
int main() {
    void* memory=nullptr;
    assert(posix_memalign(&memory, Common::LargePage, Common::LargePage)==0);
    std::memset(memory, 0xA5, Common::LargePage);
    std::int64_t physical=-1;
    assert(Common::CommitMemoryRange(memory, Common::LargePage, &physical));
    assert(physical==1337);
    for(std::size_t k=0;k<Common::LargePage;k+=4096)
        assert(static_cast<unsigned char*>(memory)[k]==0);
#ifdef EDEN_HEAP_GROWTH_TRACE
    assert(Common::timestamp_calls==4 && Common::logs==1);
#else
    assert(Common::timestamp_calls==0 && Common::logs==0);
#endif
    free(memory);
}
""".replace("__BODY__",body)
with tempfile.TemporaryDirectory(prefix="eden-heap-quiet-") as temp:
    d=Path(temp)
    cpp=d/"commit.cpp"
    cpp.write_text(fixture)
    for trace in (False, True):
        exe=d/("dev" if trace else "release")
        command=[compiler,"-std=c++20","-O1","-Wall","-Wextra","-Werror",
            "-fsanitize=address,undefined","-fno-sanitize-recover=all",
            "-DPS5_NATIVE"] + (["-DEDEN_HEAP_GROWTH_TRACE=1"] if trace else [])
        subprocess.run(command+[str(cpp),"-o",str(exe)],check=True,timeout=90)
        subprocess.run([str(exe)],check=True,timeout=90)
print("HEAP_COMMIT_QUIET_HOST_PASS real_commit=1 memset=1 trace_off=1 trace_dev_on=1 sanitizer=1")
