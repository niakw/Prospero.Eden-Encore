#!/usr/bin/env python3
"""F07 P0.4: source-extracted PS5 GPU-dirty rollback on guest readback failure."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
path=root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h"
source=path.read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
fast=(root/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(root/".github/workflows/encore-core-preflight.yml").read_text()
name="python3 -B tools/check-ps5-f07-readback-dirty-rollback-host.py"
assert name in fast and name in pre
assert "F07 restore GPU dirty image flags on readback exception" in generator
assert "F07 include uncaught exception counter for readback rollback" in generator
start=source.index("void TextureCache<P>::DownloadMemory(DAddr cpu_addr, size_t size)")
end=source.index("template <class P>", start+20)
method=source[start:end]
declaration="    boost::container::small_vector<ImageId, 16> images;\n"
guard_start=method.index("#ifdef PS5_NATIVE",method.index(declaration))
enumeration="    ForEachImageInRegion(cpu_addr, size, [this, &images]"
guard=method[guard_start:method.index(enumeration,guard_start)]
collection=method[method.index(enumeration):method.index("    if (images.empty())",method.index(enumeration))]
assert "std::uncaught_exceptions()" in guard
assert "slot_images[id].flags |= ImageFlagBits::GpuModified" in guard
native=collection[collection.index("#ifdef PS5_NATIVE"):collection.index("#else",collection.index("#ifdef PS5_NATIVE"))]
assert native.index("images.push_back(image_id)") < native.index("image.flags &= ~ImageFlagBits::GpuModified")
assert method.index(guard) < method.index(collection)
# The prior oracle remains embedded byte-for-byte; batching and Finish order
# are untouched by the guarded early flag management.
oracle=(root/"vendor/encore-active/eden-vulkan-oracles/vulkan_download_batch.inc").read_text()
assert oracle in method
cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <new>
#include <type_traits>
#include <utility>
#include <vector>
struct Maker {};
template<class F> struct Guard {F fn;~Guard(){fn();}};
template<class F> Guard<std::decay_t<F>> operator+(Maker,F&& fn) {
    return {std::forward<F>(fn)};
}
#define SCOPE_EXIT auto readback_guard = Maker{} + [&]
using ImageId=std::size_t;
using DAddr=std::size_t;
enum class ImageFlagBits:unsigned {GpuModified=1};
unsigned operator~(ImageFlagBits f) {return ~static_cast<unsigned>(f);}
unsigned& operator&=(unsigned& flags,unsigned b) {flags &= b;return flags;}
unsigned& operator|=(unsigned& flags,ImageFlagBits f) {
    flags |= static_cast<unsigned>(f);return flags;
}
struct ImageBase {unsigned flags{1};bool downloadable{true};};
struct Cache {
    std::vector<ImageBase> slot_images{{},{},{}};
    bool fail_enumeration{};
    bool fail_staging{};
    bool IsDownloadable(const ImageBase& img) const {return img.downloadable;}
    template<class F> void ForEachImageInRegion(DAddr,std::size_t,F&& fn) {
        for(ImageId id=0;id<slot_images.size();++id) {
            if(fail_enumeration && id==1)throw std::bad_alloc{};
            fn(id,slot_images[id]);
        }
    }
    void DownloadMemory(DAddr cpu_addr,std::size_t size) {
        std::vector<ImageId> images;
__SOURCE_GUARD__
__SOURCE_COLLECTION__
        if(fail_staging)throw std::bad_alloc{};
    }
};
int main(){
    Cache success;
    success.slot_images[2].downloadable=false;
    success.DownloadMemory(0,1);
    assert(success.slot_images[0].flags==0);
    assert(success.slot_images[1].flags==0);
    assert(success.slot_images[2].flags==1);
    Cache fail;
    fail.fail_staging=true;
    fail.slot_images[2].downloadable=false;
    bool caught=false;
    try {fail.DownloadMemory(0,1);} catch(const std::bad_alloc&){caught=true;}
    assert(caught);
    assert(fail.slot_images[0].flags==1);
    assert(fail.slot_images[1].flags==1);
    assert(fail.slot_images[2].flags==1);
    Cache partial;
    partial.fail_enumeration=true;
    caught=false;
    try {partial.DownloadMemory(0,1);} catch(const std::bad_alloc&){caught=true;}
    assert(caught);
    assert(partial.slot_images[0].flags==1);
    assert(partial.slot_images[1].flags==1);
    assert(partial.slot_images[2].flags==1);
}
""".replace("__SOURCE_GUARD__",guard).replace("__SOURCE_COLLECTION__",collection)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-dirty-readback-") as directory:
    path=Path(directory)/"readback.cpp"
    path.write_text(cpp)
    for opt in ("-O0","-O2"):
        exe=Path(directory)/("readback"+opt[1:])
        built=subprocess.run([compiler,"-std=c++20",opt,"-DPS5_NATIVE=1",
                              "-Wall","-Wextra","-Werror","-fsanitize=undefined",
                              "-fno-sanitize-recover=all",str(path),"-o",str(exe)],
                             capture_output=True,text=True,timeout=40)
        assert built.returncode==0,(opt,built.stderr[-5000:])
        ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
        assert ran.returncode==0,(opt,ran.stderr[-5000:])
print("F07_READBACK_DIRTY_ROLLBACK_PASS success=1 staging_exception=1 enum_exception=1 excluded=1 O0=1 O2=1")
