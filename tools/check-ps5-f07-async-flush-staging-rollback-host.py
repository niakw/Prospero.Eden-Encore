#!/usr/bin/env python3
"""F07: keep deferred Vulkan async flush staging owned until successful queue admission."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
start=source.index("void TextureCache<P>::CommitAsyncFlushes() {")
end=source.index("\ntemplate <class P>",start+20)
method=source[start:end]
assert "F07 return deferred staging when async flush batch preparation fails" in generator
assert "if (!staging_transferred) runtime.FreeDeferredStagingBuffer(download_map);" in method
assert method.index("uncommitted_async_buffers.emplace_back(download_map);") < method.index("staging_transferred = true;")
assert "auto download_map = runtime.DownloadStagingBuffer(total_size_bytes, true);" in method
for flow in (".github/workflows/encore-core-fast-gate.yml",".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-async-flush-staging-rollback-host.py" in (root/flow).read_text()
cpp=r"""
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <new>
#include <stdexcept>
#include <type_traits>
#include <utility>
#include <vector>
struct Maker {};
template<class F> struct Guard {F fn;~Guard(){fn();}};
template<class F> Guard<std::decay_t<F>> operator+(Maker,F&& fn) {
    return {std::forward<F>(fn)};
}
#define SCOPE_EXIT auto staging_guard = Maker{} + [&]
using ImageId=std::size_t;
namespace Common {
    std::size_t AlignUp(std::size_t value,std::size_t align) {
        return ((value+align-1)/align)*align;
    }
}
struct Staging {
    std::size_t buffer{};
    std::size_t offset{};
};
struct Image {
    ImageId info{};
    std::size_t unswizzled_size_bytes{128};
    bool fail_record{};
    int submitted{};
    void DownloadMemory(Staging& map,const std::vector<ImageId>& copies) {
        assert(map.buffer && copies.size()==1 && copies[0]==info);
        if(fail_record)throw std::runtime_error("GPU command recording failed");
        ++submitted;
    }
};
std::vector<ImageId> FullDownloadCopies(ImageId info) {return {info};}
std::vector<ImageId> FixSmallVectorADL(std::vector<ImageId> copies) {return copies;}
struct PendingDownload {
    bool is_swizzle{};
    std::size_t async_buffer_id{};
    ImageId object_id{};
};
struct Runtime {
    int releases{}, requests{};
    bool fail_request{};
    Staging DownloadStagingBuffer(std::size_t size,bool deferred) {
        assert(size && deferred);
        ++requests;
        if(fail_request)throw std::bad_alloc{};
        return {100,0};
    }
    void FreeDeferredStagingBuffer(Staging& buffer) {
        assert(buffer.buffer);
        ++releases;
    }
};
template<class P> struct TextureCache {
    static constexpr bool IMPLEMENTS_ASYNC_DOWNLOADS=true;
    using Image=::Image;
    std::vector<Image> slot_images;
    std::vector<PendingDownload> uncommitted_downloads;
    std::vector<Staging> uncommitted_async_buffers;
    std::deque<std::vector<PendingDownload>> committed_downloads;
    std::deque<std::vector<Staging>> async_buffers;
    Runtime runtime;
    void CommitAsyncFlushes();
};
struct NativePolicy {};
__METHOD__
TextureCache<NativePolicy> MakeCache() {
    TextureCache<NativePolicy> cache;
    cache.slot_images={{0,128,false,0},{1,96,false,0}};
    cache.uncommitted_downloads={{true,0,0},{true,0,1}};
    return cache;
}
int main() {
    auto normal=MakeCache();
    normal.CommitAsyncFlushes();
    assert(normal.uncommitted_downloads.empty());
    assert(normal.uncommitted_async_buffers.empty());
    assert(normal.committed_downloads.size()==1);
    assert(normal.committed_downloads.front().size()==2);
    assert(normal.async_buffers.size()==1 && normal.async_buffers.front().size()==1);
    assert(normal.runtime.releases==0);
    assert(normal.slot_images[0].submitted==1 && normal.slot_images[1].submitted==1);
#ifdef PS5_NATIVE
    auto rejected=MakeCache();
    rejected.runtime.fail_request=true;
    bool caught=false;
    try{rejected.CommitAsyncFlushes();}catch(const std::bad_alloc&){caught=true;}
    assert(caught && rejected.runtime.releases==0);
    assert(rejected.uncommitted_downloads.size()==2);
    assert(rejected.committed_downloads.empty() && rejected.async_buffers.empty());
    rejected.runtime.fail_request=false;
    rejected.CommitAsyncFlushes();
    assert(rejected.committed_downloads.size()==1);
    auto partial=MakeCache();
    partial.slot_images[1].fail_record=true;
    caught=false;
    try{partial.CommitAsyncFlushes();}catch(const std::runtime_error&){caught=true;}
    assert(caught && partial.runtime.releases==1);
    assert(partial.uncommitted_downloads.size()==2);
    assert(partial.uncommitted_async_buffers.empty());
    assert(partial.committed_downloads.empty() && partial.async_buffers.empty());
    partial.slot_images[1].fail_record=false;
    partial.CommitAsyncFlushes();
    assert(partial.runtime.releases==1);
    assert(partial.committed_downloads.size()==1);
#endif
}
""".replace("__METHOD__",method)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-async-batch-") as dir:
    cppfile=Path(dir)/"batch.cpp"
    cppfile.write_text(cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            out=Path(dir)/("test"+("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror","-fsanitize=undefined","-fno-sanitize-recover=all"]
            if native:cmd.append("-DPS5_NATIVE=1")
            built=subprocess.run([*cmd,str(cppfile),"-o",str(out)],capture_output=True,text=True,timeout=50)
            assert built.returncode==0,(native,opt,built.stderr[-4000:])
            run=subprocess.run([str(out)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,(native,opt,run.stderr[-4000:])
print("F07_ASYNC_FLUSH_STAGING_ROLLBACK_PASS native_desktop_O0_O2")
