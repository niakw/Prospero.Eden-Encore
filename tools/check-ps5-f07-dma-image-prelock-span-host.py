#!/usr/bin/env python3
"""F07 native DMA image invalid byte spans must not wait on both caches."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-vulkan/vulkan_rasterizer.cpp").read_text()
variant=(root/"vendor/encore-active/eden-core/guest-bridge/vulkan_rasterizer.cpp").read_text()
gen=(root/"tools/prepare-vulkan-port.py").read_text()
needle="bool AccelerateDMA::DmaBufferImageCopy("
a=source.index(needle)
b=source.index("    static constexpr auto sync_info",a)
prefix=source[a:b]
assert prefix==variant[variant.index(needle):variant.index("    static constexpr auto sync_info",variant.index(needle))]
assert "F07 native DMA image byte guard before paired cache mutex" in gen
guard=prefix.index("if (checked_bytes == 0 ||")
lock=prefix.index("std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};")
assert guard < lock
assert prefix.count("const u32 buffer_size = ")==2
for flow in (".github/workflows/encore-core-fast-gate.yml",".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-dma-image-prelock-span-host.py" in (root/flow).read_text()
cpp=r"""
#include <cassert>
#include <cstdint>
#include <mutex>
using u32=std::uint32_t;using u64=std::uint64_t;
namespace Tegra { namespace DMA {
struct ImageCopy {};
struct BufferOperand {u32 pitch{};u32 height{};u64 address{};};
struct ImageOperand {};
} }
namespace VideoCommon { constexpr int NULL_IMAGE_ID=0; }
struct CountingMutex {
    std::mutex owned;
    int requests{};
    void lock(){++requests;owned.lock();}
    bool try_lock(){++requests;return owned.try_lock();}
    void unlock(){owned.unlock();}
};
struct BufferCacheMock {CountingMutex mutex;};
struct TextureCacheMock {
    CountingMutex mutex;
    int looked_up{};
    int DmaImageId(const Tegra::DMA::ImageOperand&,bool) {
        ++looked_up;
        return 1;
    }
};
struct AccelerateDMA {
    BufferCacheMock buffer_cache;
    TextureCacheMock texture_cache;
    template<bool IS_IMAGE_UPLOAD>
    bool DmaBufferImageCopy(const Tegra::DMA::ImageCopy&,
       const Tegra::DMA::BufferOperand&,
       const Tegra::DMA::ImageOperand&);
};
"""+"template <bool IS_IMAGE_UPLOAD>\n"+prefix+"""
    (void)buffer_size;
    (void)copy_info;
    return true;
}
"""+r"""
int main(){
    for(bool upload:{false,true}){
        const auto check=[&](u32 pitch,u32 height,bool valid){
            AccelerateDMA cache;
            Tegra::DMA::BufferOperand buffer{pitch,height,7};
            Tegra::DMA::ImageCopy copy{};
            Tegra::DMA::ImageOperand image{};
            const bool ok=upload?cache.DmaBufferImageCopy<true>(copy,buffer,image)
                                :cache.DmaBufferImageCopy<false>(copy,buffer,image);
            assert(ok==valid);
#ifdef PS5_NATIVE
            if(!valid){
                assert(cache.buffer_cache.mutex.requests==0);
                assert(cache.texture_cache.mutex.requests==0);
                assert(cache.texture_cache.looked_up==0);
            } else {
                assert(cache.texture_cache.looked_up==1);
                assert(cache.buffer_cache.mutex.requests>0);
            }
#else
            if(!valid)assert(cache.texture_cache.looked_up==1);
#endif
        };
        check(0,900,false);
        check(8,0,false);
        check(0xffffffffu,2,false);
        check(64,32,true);
    }
}
"""
# The executable below already covers span validation; also pin the distinct
# Vulkan-handle guard and its position before image-cache lookup and upload.
dma_method = source[source.index(needle):source.index("\nbool AccelerateDMA::ImageToBuffer(",source.index(needle))]
dma_mirror = variant[variant.index(needle):variant.index("\nbool AccelerateDMA::ImageToBuffer(",variant.index(needle))]
assert dma_method == dma_mirror
assert dma_method.count("if (!buffer || buffer->Handle() == VK_NULL_HANDLE)") == 1
assert dma_method.index("if (!buffer || buffer->Handle() == VK_NULL_HANDLE)") < dma_method.index("texture_cache.DmaBufferImageCopy(")
assert "F07 DMA image reject null Vulkan handles" in gen
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="f07-dma-image-prelock-") as folder:
    cppfile=Path(folder)/"dma.cpp"
    cppfile.write_text(cpp)
    for opt in ("-O0","-O2"):
        for native in (True,False):
            exe=Path(folder)/(("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(["-DPS5_NATIVE=1"] if native else []),str(cppfile),"-o",str(exe)]
            build=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
            assert build.returncode==0,(native,opt,build.stderr[-4000:])
            result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert result.returncode==0,(native,opt,result.stderr[-4000:])
print("F07_DMA_IMAGE_PRELOCK_SPAN_PASS native=1 desktop=1 O0=1 O2=1 zero=1 overflow=1 valid=1 paired_mutex_skipped=1")
