#!/usr/bin/env python3
"""F07 P0.4: source-extracted native Vulkan dirty-GC fallback readback proof.

The production Cleanup readback is compiled under PS5_NATIVE and desktop.
A failed, null or short mapping must not invoke GPU download/Finish/swizzle,
nor delete the dirty image. The successful path retains its exact ordering.
Driver/Vulkan GPU operations and FC27 frametimes are host-mocked.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator=(ROOT/"tools/prepare-vulkan-port.py").read_text()
fast=(ROOT/".github/workflows/encore-core-fast-gate.yml").read_text()
pre=(ROOT/".github/workflows/encore-core-preflight.yml").read_text()
invocation="python3 -B tools/check-ps5-f07-gc-dirty-eviction-rollback-host.py"
assert invocation in fast and invocation in pre
assert "F07 leave dirty GPU image resident on failed cleanup readback" in generator
assert "F07 declare bad alloc for native dirty GC rollback" in generator
assert "F07 preserve dirty image when prefetch has no readback copy regions" in generator
assert "F07 preserve dirty image on zero-region fallback readback" in generator
begin=source.index("void TextureCache<P>::RunGarbageCollector() {")
end=source.index("\ntemplate <class P>",begin)
gc=source[begin:end]
first="        if (must_download && !UsePrefetched(image_id, image)) {"
last="        if (True(image.flags & ImageFlagBits::Tracked))"
assert gc.count(first)==gc.count(last)==1
block=gc[gc.index(first):gc.index(last)]
for expected in ("if (FullDownloadCopies(image.info).empty())", "catch (const std::bad_alloc&)",
                 "!map.buffer || map.mapped_span.size_bytes() < image.unswizzled_size_bytes",
                 "++skipped;", "image.DownloadMemory(map, copies);",
                 "runtime.Finish();", "SwizzleImage(*gpu_memory,"):
    assert expected in block,expected
assert block.index("FullDownloadCopies(image.info).empty()") < block.index("runtime.DownloadStagingBuffer")
assert gc.count("if (FullDownloadCopies(image.info).empty())") == 2
assert block.index("!map.buffer ||") < block.index("image.DownloadMemory(map,")
assert block.index("image.DownloadMemory(map,") < block.index("runtime.Finish()") < block.index("SwizzleImage(")
assert block.index("#else\n            auto map = runtime.DownloadStagingBuffer") > block.index("#ifdef PS5_NATIVE")
cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <new>
#include <span>
#include <vector>
using ImageId=std::size_t;
struct Info {bool no_regions{};};
struct GPU {};
struct Map {std::size_t buffer{}; std::span<std::uint8_t> mapped_span{};};
struct Runtime {
    bool throw_alloc{},short_map{},null_buffer{};
    unsigned allocs{},finishes{};
    std::vector<std::uint8_t> storage{};
    Map DownloadStagingBuffer(std::size_t n) {
        ++allocs;
        if(throw_alloc) throw std::bad_alloc{};
        storage.resize(n);
        return {null_buffer ? 0u : 1u,
                {storage.data(),n-(short_map ? 1u : 0u)}};
    }
    void Finish(){++finishes;}
};
struct Image {
    std::size_t unswizzled_size_bytes{8};
    std::size_t gpu_addr{1024};
    Info info{};
    unsigned downloads{};
    void DownloadMemory(Map& map,std::vector<int> copies) {
        assert(!copies.empty());
        assert(map.mapped_span.size()>=unswizzled_size_bytes);
        ++downloads;
        map.mapped_span.front()=19;
    }
};
std::vector<int> FullDownloadCopies(Info info){
    return info.no_regions ? std::vector<int>{} : std::vector<int>{1};
}
std::vector<int> FixSmallVectorADL(std::vector<int> n){return n;}
unsigned swizzle_calls{};
void SwizzleImage(GPU&,std::size_t,Info,std::vector<int> copies,std::span<std::uint8_t> bytes,
                  std::vector<std::uint8_t>&) {
    assert(!copies.empty() && bytes.size()>=8 && bytes.front()==19);
    ++swizzle_calls;
}
struct Cache {
    Runtime runtime{};
    GPU gpu{},*gpu_memory=&gpu;
    Image image{};
    std::vector<std::uint8_t> swizzle_data_buffer{};
    bool prefetched{};
    unsigned skipped{},deletions{};
    bool UsePrefetched(ImageId,Image&){return prefetched;}
    bool Cleanup() {
        const ImageId image_id=1;
        const bool must_download=true;
        Image& image=this->image;
__SOURCE_GC_FALLBACK__
        ++deletions;
        return true;
    }
};
int main(){
    Cache good;
    assert(good.Cleanup());
    assert(good.deletions==1 && good.skipped==0);
    assert(good.image.downloads==1 && good.runtime.finishes==1);
    assert(good.runtime.allocs==1 && swizzle_calls==1);
    Cache prefetched;
    prefetched.prefetched=true;
    assert(prefetched.Cleanup() && prefetched.deletions==1);
    assert(prefetched.runtime.allocs==0 && prefetched.runtime.finishes==0);
#ifdef PS5_NATIVE
    Cache no_regions;
    no_regions.image.info.no_regions = true;
    assert(!no_regions.Cleanup());
    assert(no_regions.deletions==0 && no_regions.skipped==1);
    assert(no_regions.runtime.allocs==0 && no_regions.image.downloads==0);
    Cache rejected;
    rejected.runtime.throw_alloc=true;
    assert(!rejected.Cleanup());
    assert(rejected.deletions==0 && rejected.skipped==1);
    assert(rejected.image.downloads==0 && rejected.runtime.finishes==0);
    Cache short_map;
    short_map.runtime.short_map=true;
    assert(!short_map.Cleanup());
    assert(short_map.deletions==0 && short_map.skipped==1);
    assert(short_map.image.downloads==0 && short_map.runtime.finishes==0);
    Cache missing;
    missing.runtime.null_buffer=true;
    assert(!missing.Cleanup());
    assert(missing.deletions==0 && missing.skipped==1);
    assert(missing.image.downloads==0 && missing.runtime.finishes==0);
    assert(swizzle_calls==1);
#endif
}
""".replace("__SOURCE_GC_FALLBACK__",block)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-dirty-gc-") as folder:
    path=Path(folder)/"gc.cpp"
    path.write_text(cpp)
    for opt in ("-O0","-O2"):
        for native in (False,True):
            exe=Path(folder)/("gc"+opt[1:]+("-ps5" if native else "-desktop"))
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 *(['-DPS5_NATIVE=1'] if native else []),
                 str(path),"-o",str(exe)]
            built=subprocess.run(cmd,capture_output=True,text=True,timeout=40)
            assert built.returncode==0,(native,opt,built.stderr[-6000:])
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert ran.returncode==0,(native,opt,ran.stderr[-5000:])
print("F07_GC_DIRTY_EVICTION_ROLLBACK_PASS native_short=1 null=1 oom=1 no_delete=1 valid_finish=1 prefetched=1 desktop_original=1 O0=1 O2=1")
