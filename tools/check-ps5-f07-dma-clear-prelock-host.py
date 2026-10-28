#!/usr/bin/env python3
"""Source-extracted PS5 DMA clear guard: zero/oversize requests avoid cache mutex."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
active=(root/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
bridge=(root/"vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp").read_text()
core=(root/"vendor/encore-active/eden-core/src/video_core/buffer_cache/buffer_cache.h").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
a="bool AccelerateDMA::BufferClear("
b="\nbool AccelerateDMA::BufferCopy("
def extract(text):
    start=text.index(a)
    return text[start:text.index(b,start)]
method=extract(active)
assert method==extract(bridge)
guard="if (amount == 0 || amount > static_cast<u64>(~u32{0}) / sizeof(u32))"
assert guard in method
assert method.index(guard) < method.index("std::scoped_lock lock{buffer_cache.mutex};")
assert "#ifdef PS5_NATIVE" in method and "#endif" in method
core_start=core.index("bool BufferCache<P>::DMAClear(")
core_guard=core[core_start:core.index("\ntemplate <class P>",core_start)]
assert guard in core_guard
assert "F07 reject invalid DMA clear words before the buffer mutex" in generator
for path in (".github/workflows/encore-core-fast-gate.yml",
             ".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-dma-clear-prelock-host.py" in (root/path).read_text()

cpp=r"""
#include <cassert>
#include <cstdint>
#include <mutex>
using u32=std::uint32_t;
using u64=std::uint64_t;
using GPUVAddr=u64;
struct CountMutex {
    std::mutex mutex;
    unsigned locks{};
    void lock() { ++locks; mutex.lock(); }
    void unlock() { mutex.unlock(); }
};
struct BufferCache {
    CountMutex mutex;
    unsigned dma_calls{};
    bool DMAClear(GPUVAddr, u64 count, u32) {
        ++dma_calls;
        return count != 0 && count <= static_cast<u64>(~u32{0})/sizeof(u32);
    }
};
struct AccelerateDMA {
    BufferCache buffer_cache;
    bool BufferClear(GPUVAddr,u64,u32);
};
""" + method + r"""
int main() {
    constexpr u64 valid_max=static_cast<u64>(~u32{0})/sizeof(u32);
    const auto check=[](u64 words,bool accepted,bool locked) {
        AccelerateDMA dma;
        const bool ok=dma.BufferClear(77,words,0xdeadbeefu);
        assert(ok==accepted);
        assert((dma.buffer_cache.mutex.locks != 0)==locked);
        assert((dma.buffer_cache.dma_calls != 0)==locked);
    };
#ifdef PS5_NATIVE
    check(0,false,false);
    check(valid_max+1,false,false);
    check(static_cast<u64>(~u32{0}),false,false);
#else
    check(0,false,true);
    check(valid_max+1,false,true);
    check(static_cast<u64>(~u32{0}),false,true);
#endif
    check(1,true,true);
    check(valid_max,true,true);
}
"""
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="f07-clear-prelock-") as folder:
    src=Path(folder)/"clear.cpp"
    src.write_text(cpp)
    for native in (True,False):
        for opt in ("-O0","-O2"):
            exe=Path(folder)/(("native" if native else "desktop")+opt[1:])
            flags=["-DPS5_NATIVE=1"] if native else []
            build=subprocess.run([compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                                  "-fsanitize=undefined","-fno-sanitize-recover=all",
                                  *flags,str(src),"-o",str(exe)],capture_output=True,text=True,timeout=45)
            assert build.returncode==0,(native,opt,build.stderr[-4000:])
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-4000:])
print("F07_DMA_CLEAR_PRELOCK_PASS ps5_no_mutex_on_invalid=1 desktop_original=1 max_words=1 overflow=1 O0=1 O2=1 UBSan=1")
