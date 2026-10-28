#!/usr/bin/env python3
"""F07 PS5: reverse async-DMA reservations when staged readback fails."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
source=(root/"vendor/encore-active/eden-vulkan/vulkan-cache/video_core/texture_cache/texture_cache.h").read_text()
generator=(root/"tools/prepare-vulkan-port.py").read_text()
start=source.index("void TextureCache<P>::DownloadImageIntoBuffer(")
end=source.index("\ntemplate <class P>",start+20)
method=source[start:end]
assert "F07 rollback asynchronous DMA slot and staging on failed guest readback" in generator
assert "slot_buffer_downloads.erase(slot);" in method
assert "runtime.FreeDeferredStagingBuffer(uncommitted_async_buffers.back());" in method
assert "runtime.FreeDeferredStagingBuffer(download_map);" in method
assert "if (!download_submitted)" in method
assert method.index("download_submitted = true;") > method.index("image->DownloadMemory(buffers, buffer_offsets, copies);")
for flow in (".github/workflows/encore-core-fast-gate.yml",".github/workflows/encore-core-preflight.yml"):
    assert "python3 -B tools/check-ps5-f07-async-dma-rollback-host.py" in (root/flow).read_text()
cpp=r"""
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <new>
#include <span>
#include <stdexcept>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <vector>
using GPUVAddr=std::size_t;
namespace VideoCommon {struct BufferImageCopy {};}
struct Maker {};
template<class F> struct Guard {F fn;~Guard(){fn();}};
template<class F> Guard<std::decay_t<F>> operator+(Maker,F&& f) {
    return {std::forward<F>(f)};
}
#define SCOPE_EXIT auto cleanup_guard = Maker{} + [&]
struct BufferDownload {GPUVAddr addr;std::size_t size;};
struct PendingDownload {bool is_swizzle;std::size_t async_buffer_id;std::size_t object_id;};
struct SlotTable {
    std::size_t next{};
    std::unordered_map<std::size_t,BufferDownload> active;
    std::size_t insert(BufferDownload b) {
        const auto slot=next++;
        active.emplace(slot,b);
        return slot;
    }
    void erase(std::size_t slot) {assert(active.erase(slot)==1);}
};
struct Staging {std::size_t buffer{};std::size_t offset{};};
struct Runtime {
    bool fail_staging{};
    int releases{};
    Staging DownloadStagingBuffer(std::size_t size,bool deferred) {
        assert(size && deferred);
        if(fail_staging)throw std::bad_alloc{};
        return {100,0};
    }
    void FreeDeferredStagingBuffer(Staging& map) {
        assert(map.buffer);
        ++releases;
    }
};
struct Image {
    bool fail_submission{};
    template<class Buffers,class Offsets>
    void DownloadMemory(Buffers buffers,Offsets offsets,
                        std::span<const VideoCommon::BufferImageCopy> copies) {
        assert(buffers[0]==21 && buffers[1]==100);
        assert(offsets[0]==7 && offsets[1]==0);
        assert(copies.empty());
        if(fail_submission)throw std::runtime_error("recording rejected");
    }
};
template<class P> struct TextureCache {
    using Image=::Image;
    using BufferType=std::size_t;
    static constexpr bool IMPLEMENTS_ASYNC_DOWNLOADS=true;
    SlotTable slot_buffer_downloads;
    std::vector<PendingDownload> uncommitted_downloads;
    std::vector<Staging> uncommitted_async_buffers;
    Runtime runtime;
    void DownloadImageIntoBuffer(Image* image,BufferType buffer,
                                 std::size_t buffer_offset,
                                 std::span<const VideoCommon::BufferImageCopy> copies,
                                 GPUVAddr address,std::size_t size);
};
struct NativePolicy {};
__METHOD__
int main() {
    TextureCache<NativePolicy> ok;
    Image good;
    ok.DownloadImageIntoBuffer(&good,21,7,{},1000,128);
    assert(ok.slot_buffer_downloads.active.size()==1);
    assert(ok.uncommitted_downloads.size()==1);
    assert(ok.uncommitted_async_buffers.size()==1);
    assert(ok.runtime.releases==0);
#ifdef PS5_NATIVE
    TextureCache<NativePolicy> rejected;
    rejected.runtime.fail_staging=true;
    bool threw=false;
    try {rejected.DownloadImageIntoBuffer(&good,21,7,{},1000,128);}
    catch(const std::bad_alloc&) {threw=true;}
    assert(threw);
    assert(rejected.slot_buffer_downloads.active.empty());
    assert(rejected.uncommitted_downloads.empty());
    assert(rejected.uncommitted_async_buffers.empty());
    assert(rejected.runtime.releases==0);
    TextureCache<NativePolicy> failed_submission;
    Image bad;
    bad.fail_submission=true;
    threw=false;
    try {failed_submission.DownloadImageIntoBuffer(&bad,21,7,{},1000,128);}
    catch(const std::runtime_error&) {threw=true;}
    assert(threw);
    assert(failed_submission.slot_buffer_downloads.active.empty());
    assert(failed_submission.uncommitted_downloads.empty());
    assert(failed_submission.uncommitted_async_buffers.empty());
    assert(failed_submission.runtime.releases==1);
#endif
}
""".replace("__METHOD__", "template<class P>\n" + method)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler,"C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-f07-async-dma-") as folder:
    path=Path(folder)/"test.cpp"
    path.write_text(cpp)
    for native in (False,True):
        for opt in ("-O0","-O2"):
            exe=Path(folder)/("test"+("native" if native else "desktop")+opt[1:])
            cmd=[compiler,"-std=c++20",opt,"-Wall","-Wextra","-Werror","-fsanitize=undefined","-fno-sanitize-recover=all"]
            if native:cmd.append("-DPS5_NATIVE=1")
            compiled=subprocess.run([*cmd,str(path),"-o",str(exe)],
                                    capture_output=True,text=True,timeout=45)
            assert compiled.returncode==0,(native,opt,compiled.stderr[-4000:])
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert ran.returncode==0,(native,opt,ran.stderr[-4000:])
print("F07_ASYNC_DMA_ROLLBACK_PASS PS5_DESKTOP_O0_O2 staging_failure=1 submission_failure=1")
