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
pop_start=source.index("void TextureCache<P>::PopAsyncFlushes() {",end)
pop_end=source.index("\ntemplate <class P>",pop_start+20)
pop=source[pop_start:pop_end]
empty_start=pop.index("        if (download_ids.empty()) {")
empty_end=pop.index("\n#ifdef PS5_NATIVE\n        // Keep staging queued",empty_start)
empty_pop=pop[empty_start:empty_end]
assert "F07 return deferred staging when async flush batch preparation fails" in generator
assert "F07 rollback async download queue pair on second insertion failure" in generator
assert "F07 release deferred staging from empty async download batch" in generator
assert "F07 guard overflow before async swizzle staging allocation" in generator
assert "if (bytes > max_bytes - 63)" in method
assert "if (aligned_bytes > max_bytes - total_size_bytes)" in method
assert method.index("if (bytes > max_bytes - 63)") < method.index("runtime.DownloadStagingBuffer(total_size_bytes, true)")
assert "runtime.FreeDeferredStagingBuffer(buffer);" in empty_pop
assert empty_pop.index("runtime.FreeDeferredStagingBuffer(buffer);") < empty_pop.index("committed_downloads.pop_front();")
assert "const size_t initial_staging_count = uncommitted_async_buffers.size();" in method
assert "committed_downloads.emplace_back(std::move(uncommitted_downloads));" in method
assert "uncommitted_async_buffers = std::move(async_buffers.back());" in method
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
#include <limits>
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
    struct CommittedQueue {
        std::deque<std::vector<PendingDownload>> values;
        bool reject_next{};
        template<class T> void emplace_back(T&& item) {
            if (reject_next) {
                reject_next=false;
                throw std::bad_alloc{};
            }
            values.emplace_back(std::forward<T>(item));
        }
        bool empty() const {return values.empty();}
        void pop_front() {values.pop_front();}
        std::size_t size() const {return values.size();}
        const std::vector<PendingDownload>& front() const {return values.front();}
    } committed_downloads;
    std::deque<std::vector<Staging>> async_buffers;
    Runtime runtime;
    void CommitAsyncFlushes();
    void PopEmptyAsyncFlushes() {
        const auto& download_ids = committed_downloads.front();
__EMPTY_POP__
    }
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
    // A second deque allocation can fail after async_buffers accepted its
    // matching vector. Both queues must remain aligned and retryable.
    auto pair_failure=MakeCache();
    pair_failure.committed_downloads.reject_next=true;
    caught=false;
    try{pair_failure.CommitAsyncFlushes();}catch(const std::bad_alloc&){caught=true;}
    assert(caught && pair_failure.runtime.releases==1);
    assert(pair_failure.committed_downloads.empty() && pair_failure.async_buffers.empty());
    assert(pair_failure.uncommitted_downloads.size()==2);
    assert(pair_failure.uncommitted_async_buffers.empty());
    pair_failure.CommitAsyncFlushes();
    assert(pair_failure.committed_downloads.size()==1);
    assert(pair_failure.async_buffers.size()==1 && pair_failure.async_buffers.front().size()==1);
    // An empty pending batch may still have staged DMA sources; failed
    // publication must never release or orphan those earlier buffers.
    TextureCache<NativePolicy> empty_batch;
    empty_batch.uncommitted_async_buffers.push_back({777,0});
    empty_batch.committed_downloads.reject_next=true;
    caught=false;
    try{empty_batch.CommitAsyncFlushes();}catch(const std::bad_alloc&){caught=true;}
    assert(caught && empty_batch.runtime.releases==0);
    assert(empty_batch.committed_downloads.empty() && empty_batch.async_buffers.empty());
    assert(empty_batch.uncommitted_async_buffers.size()==1);
    assert(empty_batch.uncommitted_async_buffers.front().buffer==777);
    empty_batch.CommitAsyncFlushes();
    assert(empty_batch.committed_downloads.size()==1 && empty_batch.async_buffers.size()==1);
    assert(empty_batch.async_buffers.front()[0].buffer==777);
    empty_batch.PopEmptyAsyncFlushes();
    assert(empty_batch.runtime.releases==1);
    assert(empty_batch.committed_downloads.empty() && empty_batch.async_buffers.empty());
    TextureCache<NativePolicy> harmless_empty;
    harmless_empty.CommitAsyncFlushes();
    harmless_empty.PopEmptyAsyncFlushes();
    assert(harmless_empty.runtime.releases==0);
    // No host staging request or async queue mutation when aligning a
    // hostile 3D byte count would wrap size_t.
    const auto max_size=(std::numeric_limits<std::size_t>::max)();
    auto align_overflow=MakeCache();
    align_overflow.slot_images[0].unswizzled_size_bytes=max_size-31;
    caught=false;
    try{align_overflow.CommitAsyncFlushes();}catch(const std::bad_alloc&){caught=true;}
    assert(caught && align_overflow.runtime.requests==0);
    assert(align_overflow.runtime.releases==0);
    assert(align_overflow.uncommitted_downloads.size()==2);
    assert(align_overflow.committed_downloads.empty() && align_overflow.async_buffers.empty());
    // Each image fits alone, but their aligned aggregate cannot fit.
    auto sum_overflow=MakeCache();
    sum_overflow.slot_images[0].unswizzled_size_bytes=max_size-127;
    caught=false;
    try{sum_overflow.CommitAsyncFlushes();}catch(const std::bad_alloc&){caught=true;}
    assert(caught && sum_overflow.runtime.requests==0);
    assert(sum_overflow.runtime.releases==0);
    assert(sum_overflow.uncommitted_downloads.size()==2);
    assert(sum_overflow.committed_downloads.empty() && sum_overflow.async_buffers.empty());
#endif
}
""".replace("__METHOD__", "template<class P>\n" + method).replace("__EMPTY_POP__", empty_pop)
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
